"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.initializeTelemetry = initializeTelemetry;
exports.createCustomSpan = createCustomSpan;
exports.shutdownTelemetry = shutdownTelemetry;
const sdk_node_1 = require("@opentelemetry/sdk-node");
const auto_instrumentations_node_1 = require("@opentelemetry/auto-instrumentations-node");
const resources_1 = require("@opentelemetry/resources");
const semantic_conventions_1 = require("@opentelemetry/semantic-conventions");
const api_1 = require("@opentelemetry/api");
let sdk;
function initializeTelemetry() {
    if (sdk) {
        return;
    }
    const resource = new resources_1.Resource({
        [semantic_conventions_1.SEMRESATTRS_SERVICE_NAME]: process.env.OTEL_SERVICE_NAME || 'github-release-crawler',
        [semantic_conventions_1.SEMRESATTRS_SERVICE_VERSION]: process.env.OTEL_SERVICE_VERSION || '1.0.0',
    });
    // Use environment variables for OTEL configuration
    // The SDK will automatically pick up OTEL_EXPORTER_OTLP_ENDPOINT and other env vars
    sdk = new sdk_node_1.NodeSDK({
        resource,
        instrumentations: [(0, auto_instrumentations_node_1.getNodeAutoInstrumentations)({
                '@opentelemetry/instrumentation-fs': {
                    enabled: false,
                },
            })],
    });
    sdk.start();
    const endpoint = process.env.OTEL_EXPORTER_OTLP_TRACES_ENDPOINT || process.env.OTEL_EXPORTER_OTLP_ENDPOINT || 'http://localhost:4318/v1/traces';
    const serviceName = process.env.OTEL_SERVICE_NAME || 'github-release-crawler';
    console.log('🔧 OpenTelemetry Configuration:');
    console.log('  Service Name:', serviceName);
    console.log('  Service Version:', process.env.OTEL_SERVICE_VERSION || '1.0.0');
    console.log('  Export Endpoint:', endpoint);
    console.log('  OTLP Headers:', process.env.OTEL_EXPORTER_OTLP_HEADERS || 'none');
    console.log('  Traces Exporter:', process.env.OTEL_TRACES_EXPORTER || 'otlp');
    // Create a test span to verify exporting works
    setTimeout(() => {
        createTestSpan();
    }, 2000); // Wait 2 seconds for SDK to fully initialize
    // Log export attempts every 10 seconds for debugging
    setInterval(() => {
        const tracer = api_1.trace.getTracer(process.env.OTEL_SERVICE_NAME || 'porter', '1.0.0');
        const span = tracer.startSpan('debug-heartbeat', {
            attributes: {
                'debug.type': 'heartbeat',
                'debug.timestamp': Date.now()
            }
        });
        span.end();
        console.log('💗 Debug heartbeat span created (should appear in OTEL collector)');
    }, 30000); // Every 30 seconds
}
function createTestSpan() {
    const tracer = api_1.trace.getTracer(process.env.OTEL_SERVICE_NAME || 'porter', '1.0.0');
    console.log('📊 Creating test span to verify OTEL export...');
    const span = tracer.startSpan('telemetry-test-span', {
        attributes: {
            'test.type': 'initialization',
            'test.timestamp': Date.now(),
            'service.name': process.env.OTEL_SERVICE_NAME || 'github-release-crawler'
        }
    });
    span.addEvent('Test span created', {
        'event.type': 'test',
        'event.message': 'Verifying OTEL export functionality'
    });
    span.setStatus({ code: api_1.SpanStatusCode.OK, message: 'Test span completed successfully' });
    span.end();
    console.log('✅ Test span created and ended. Check your OTEL collector logs for export confirmation.');
}
function createCustomSpan(name, operation) {
    const tracer = api_1.trace.getTracer(process.env.OTEL_SERVICE_NAME || 'porter', '1.0.0');
    return tracer.startActiveSpan(name, async (span) => {
        try {
            console.log(`📈 Starting span: ${name}`);
            const result = await operation();
            span.setStatus({ code: api_1.SpanStatusCode.OK });
            console.log(`✅ Span completed: ${name}`);
            return result;
        }
        catch (error) {
            console.log(`❌ Span failed: ${name}`, error);
            span.recordException(error);
            span.setStatus({ code: api_1.SpanStatusCode.ERROR, message: error.message });
            throw error;
        }
        finally {
            span.end();
        }
    });
}
function shutdownTelemetry() {
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
//# sourceMappingURL=telemetry.js.map