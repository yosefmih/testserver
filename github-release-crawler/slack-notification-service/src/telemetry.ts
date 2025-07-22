import { NodeSDK } from '@opentelemetry/sdk-node';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';
import { Resource } from '@opentelemetry/resources';
import { SEMRESATTRS_SERVICE_NAME, SEMRESATTRS_SERVICE_VERSION } from '@opentelemetry/semantic-conventions';
import { trace, SpanStatusCode, context } from '@opentelemetry/api';

let sdk: NodeSDK;

export function initializeTelemetry(): void {
  if (sdk) {
    return;
  }

  const resource = new Resource({
    [SEMRESATTRS_SERVICE_NAME]: process.env.OTEL_SERVICE_NAME || 'slack-notification-service',
    [SEMRESATTRS_SERVICE_VERSION]: process.env.OTEL_SERVICE_VERSION || '1.0.0',
  });

  sdk = new NodeSDK({
    resource,
    instrumentations: [getNodeAutoInstrumentations({
      '@opentelemetry/instrumentation-fs': {
        enabled: false,
      },
    })],
  });

  sdk.start();
  
  const endpoint = process.env.OTEL_EXPORTER_OTLP_TRACES_ENDPOINT || process.env.OTEL_EXPORTER_OTLP_ENDPOINT || 'http://localhost:4318/v1/traces';
  const serviceName = process.env.OTEL_SERVICE_NAME || 'slack-notification-service';
  
  console.log('🔧 OpenTelemetry Configuration:');
  console.log('  Service Name:', serviceName);
  console.log('  Service Version:', process.env.OTEL_SERVICE_VERSION || '1.0.0');
  console.log('  Export Endpoint:', endpoint);
  console.log('  OTLP Headers:', process.env.OTEL_EXPORTER_OTLP_HEADERS || 'none');
  console.log('  Traces Exporter:', process.env.OTEL_TRACES_EXPORTER || 'otlp');
  
  // Create a test span to verify exporting works
  setTimeout(() => {
    createTestSpan();
  }, 2000);
  
  // Debug heartbeat spans
  setInterval(() => {
    const tracer = trace.getTracer(process.env.OTEL_SERVICE_NAME || 'porter', '1.0.0');
    const span = tracer.startSpan('debug-heartbeat', {
      attributes: {
        'debug.type': 'heartbeat',
        'debug.timestamp': Date.now(),
        'service.name': serviceName
      }
    });
    span.end();
    console.log('💗 Debug heartbeat span created (should appear in OTEL collector)');
  }, 30000);
}

function createTestSpan(): void {
  const tracer = trace.getTracer(process.env.OTEL_SERVICE_NAME || 'porter', '1.0.0');
  
  console.log('📊 Creating test span to verify OTEL export...');
  
  const span = tracer.startSpan('telemetry-test-span', {
    attributes: {
      'test.type': 'initialization',
      'test.timestamp': Date.now(),
      'service.name': process.env.OTEL_SERVICE_NAME || 'slack-notification-service'
    }
  });
  
  span.addEvent('Test span created', {
    'event.type': 'test',
    'event.message': 'Verifying OTEL export functionality for notification service'
  });
  
  span.setStatus({ code: SpanStatusCode.OK, message: 'Test span completed successfully' });
  span.end();
  
  console.log('✅ Test span created and ended. Check your OTEL collector logs for export confirmation.');
}

export function createTracedOperation<T>(name: string, operation: () => Promise<T> | T, attributes?: Record<string, string | number | boolean>): Promise<T> {
  const tracer = trace.getTracer(process.env.OTEL_SERVICE_NAME || 'porter', '1.0.0');
  
  return tracer.startActiveSpan(name, async (span) => {
    try {
      if (attributes) {
        span.setAttributes(attributes);
      }
      
      console.log(`📈 Starting span: ${name}`);
      const result = await operation();
      span.setStatus({ code: SpanStatusCode.OK });
      console.log(`✅ Span completed: ${name}`);
      return result;
    } catch (error) {
      console.log(`❌ Span failed: ${name}`, error);
      span.recordException(error as Error);
      span.setStatus({ code: SpanStatusCode.ERROR, message: (error as Error).message });
      throw error;
    } finally {
      span.end();
    }
  });
}

// Helper to propagate trace context from HTTP headers
export function extractTraceContext(headers: Record<string, string | string[] | undefined>): any {
  const traceparent = headers['traceparent'] as string;
  const requestId = headers['x-request-id'] as string;
  
  if (traceparent) {
    console.log('🔗 Received trace context from upstream service:', traceparent);
    
    // The Express auto-instrumentation should handle traceparent automatically
    // but we can ensure it's properly propagated by logging it
    if (requestId) {
      console.log('🔗 Request ID for trace correlation:', requestId);
    }
  } else {
    console.log('🔍 No traceparent header found in request');
  }
  
  return context.active();
}

export function shutdownTelemetry(): Promise<void> {
  if (sdk) {
    return sdk.shutdown();
  }
  return Promise.resolve();
}

process.on('SIGTERM', () => {
  shutdownTelemetry()
    .finally(() => process.exit(0));
});

process.on('SIGINT', () => {
  shutdownTelemetry()
    .finally(() => process.exit(0));
});