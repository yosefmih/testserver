import React, { useState, useEffect } from 'react';
import { Activity, Clock, GitBranch, MessageSquare, ExternalLink, RefreshCw, AlertCircle } from 'lucide-react';

interface TraceSpan {
  service: string;
  operation: string;
  duration: number;
  status: 'success' | 'error' | 'pending';
  timestamp: string;
  attributes?: Record<string, any>;
}

interface DistributedTrace {
  trace_id: string;
  repository: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  status: 'completed' | 'failed' | 'in_progress';
  started_at: string;
  completed_at?: string;
  spans: TraceSpan[];
  total_duration: number;
}

const TraceViewer: React.FC = () => {
  const [traces, setTraces] = useState<DistributedTrace[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedTrace, setSelectedTrace] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Mock data for demonstration since we don't have a trace storage backend yet
  const generateMockTraces = (): DistributedTrace[] => {
    const mockTraces: DistributedTrace[] = [
      {
        trace_id: 'frontend-1703123456789-abc123def',
        repository: 'microsoft/TypeScript',
        severity: 'medium',
        status: 'completed',
        started_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
        completed_at: new Date(Date.now() - 4 * 60 * 1000).toISOString(),
        total_duration: 62340,
        spans: [
          {
            service: 'frontend',
            operation: 'submit-analysis-request',
            duration: 245,
            status: 'success',
            timestamp: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
            attributes: { 'http.method': 'POST', 'user.action': 'submit_form' }
          },
          {
            service: 'github-release-crawler',
            operation: 'analyze-releases',
            duration: 45230,
            status: 'success',
            timestamp: new Date(Date.now() - 5 * 60 * 1000 + 300).toISOString(),
            attributes: { 'github.repo': 'microsoft/TypeScript', 'analysis.version': '5.0.0' }
          },
          {
            service: 'anthropic-llm',
            operation: 'analyze-breaking-changes',
            duration: 15680,
            status: 'success',
            timestamp: new Date(Date.now() - 4.5 * 60 * 1000).toISOString(),
            attributes: { 'llm.model': 'claude-3-sonnet', 'analysis.breaking_changes': 3 }
          },
          {
            service: 'slack-notification-service',
            operation: 'send-notification',
            duration: 1185,
            status: 'success',
            timestamp: new Date(Date.now() - 4.2 * 60 * 1000).toISOString(),
            attributes: { 'slack.channel': '#releases', 'notification.type': 'breaking_changes' }
          }
        ]
      },
      {
        trace_id: 'frontend-1703123456789-xyz789uvw',
        repository: 'facebook/react',
        severity: 'high',
        status: 'failed',
        started_at: new Date(Date.now() - 15 * 60 * 1000).toISOString(),
        total_duration: 5340,
        spans: [
          {
            service: 'frontend',
            operation: 'submit-analysis-request',
            duration: 189,
            status: 'success',
            timestamp: new Date(Date.now() - 15 * 60 * 1000).toISOString(),
            attributes: { 'http.method': 'POST' }
          },
          {
            service: 'github-release-crawler',
            operation: 'analyze-releases',
            duration: 2340,
            status: 'error',
            timestamp: new Date(Date.now() - 15 * 60 * 1000 + 200).toISOString(),
            attributes: { 'error.message': 'Rate limit exceeded', 'github.repo': 'facebook/react' }
          },
          {
            service: 'slack-notification-service',
            operation: 'send-error-notification',
            duration: 2811,
            status: 'success',
            timestamp: new Date(Date.now() - 14.9 * 60 * 1000).toISOString(),
            attributes: { 'slack.channel': '#alerts', 'notification.type': 'error' }
          }
        ]
      },
      {
        trace_id: 'frontend-1703123456789-pqr456mno',
        repository: 'vercel/next.js',
        severity: 'low',
        status: 'in_progress',
        started_at: new Date(Date.now() - 2 * 60 * 1000).toISOString(),
        total_duration: 0,
        spans: [
          {
            service: 'frontend',
            operation: 'submit-analysis-request',
            duration: 156,
            status: 'success',
            timestamp: new Date(Date.now() - 2 * 60 * 1000).toISOString(),
            attributes: { 'http.method': 'POST' }
          },
          {
            service: 'github-release-crawler',
            operation: 'analyze-releases',
            duration: 0,
            status: 'pending',
            timestamp: new Date(Date.now() - 2 * 60 * 1000 + 200).toISOString(),
            attributes: { 'github.repo': 'vercel/next.js', 'status': 'fetching_releases' }
          }
        ]
      }
    ];
    return mockTraces;
  };

  const fetchTraces = async () => {
    setLoading(true);
    setError(null);
    
    try {
      // Simulate API call delay
      await new Promise(resolve => setTimeout(resolve, 800));
      
      // In a real implementation, this would call an API
      // const response = await axios.get('/api/traces');
      // setTraces(response.data.traces);
      
      setTraces(generateMockTraces());
    } catch (err) {
      setError('Failed to fetch traces');
      console.error('Error fetching traces:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTraces();
  }, []);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'text-green-600 bg-green-100';
      case 'failed': return 'text-red-600 bg-red-100';
      case 'in_progress': return 'text-blue-600 bg-blue-100';
      default: return 'text-gray-600 bg-gray-100';
    }
  };

  const getServiceIcon = (service: string) => {
    switch (service) {
      case 'frontend': return <ExternalLink className="w-4 h-4" />;
      case 'github-release-crawler': return <GitBranch className="w-4 h-4" />;
      case 'slack-notification-service': return <MessageSquare className="w-4 h-4" />;
      case 'anthropic-llm': return <Activity className="w-4 h-4" />;
      default: return <Activity className="w-4 h-4" />;
    }
  };

  const formatDuration = (ms: number) => {
    if (ms === 0) return 'Pending';
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${(ms / 60000).toFixed(1)}m`;
  };

  const selectedTraceData = traces.find(t => t.trace_id === selectedTrace);

  if (loading && traces.length === 0) {
    return (
      <div className="flex justify-center items-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h3 className="text-lg font-medium text-gray-900">Recent Traces</h3>
          <p className="text-sm text-gray-600">
            End-to-end request tracing across all microservices
          </p>
        </div>
        <button
          onClick={fetchTraces}
          disabled={loading}
          className="inline-flex items-center px-3 py-2 border border-gray-300 shadow-sm text-sm leading-4 font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Error State */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center space-x-2">
          <AlertCircle className="w-5 h-5 text-red-600" />
          <span className="text-red-800">{error}</span>
        </div>
      )}

      {/* Trace List */}
      <div className="bg-white shadow rounded-lg overflow-hidden">
        <div className="divide-y divide-gray-200">
          {traces.map((trace) => (
            <div
              key={trace.trace_id}
              className={`p-6 hover:bg-gray-50 cursor-pointer transition-colors ${
                selectedTrace === trace.trace_id ? 'bg-blue-50 border-l-4 border-blue-500' : ''
              }`}
              onClick={() => setSelectedTrace(selectedTrace === trace.trace_id ? null : trace.trace_id)}
            >
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <div className="flex items-center space-x-3 mb-2">
                    <h4 className="text-sm font-medium text-gray-900">
                      {trace.repository}
                    </h4>
                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusColor(trace.status)}`}>
                      {trace.status.replace('_', ' ').toUpperCase()}
                    </span>
                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                      trace.severity === 'critical' ? 'text-red-600 bg-red-100' :
                      trace.severity === 'high' ? 'text-orange-600 bg-orange-100' :
                      trace.severity === 'medium' ? 'text-yellow-600 bg-yellow-100' :
                      'text-green-600 bg-green-100'
                    }`}>
                      {trace.severity.toUpperCase()}
                    </span>
                  </div>
                  
                  <div className="flex items-center space-x-4 text-sm text-gray-500">
                    <span className="font-mono">{trace.trace_id}</span>
                    <span className="flex items-center">
                      <Clock className="w-4 h-4 mr-1" />
                      {formatDuration(trace.total_duration)}
                    </span>
                    <span>{trace.spans.length} spans</span>
                    <span>{new Date(trace.started_at).toLocaleString()}</span>
                  </div>
                </div>
                
                <div className="flex items-center space-x-2">
                  {trace.spans.slice(0, 4).map((span, index) => (
                    <div
                      key={index}
                      className={`w-8 h-8 rounded-full flex items-center justify-center ${
                        span.status === 'success' ? 'bg-green-100 text-green-600' :
                        span.status === 'error' ? 'bg-red-100 text-red-600' :
                        'bg-gray-100 text-gray-600'
                      }`}
                      title={`${span.service}: ${span.operation}`}
                    >
                      {getServiceIcon(span.service)}
                    </div>
                  ))}
                  {trace.spans.length > 4 && (
                    <div className="text-xs text-gray-500">
                      +{trace.spans.length - 4}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Trace Details */}
      {selectedTraceData && (
        <div className="bg-white shadow rounded-lg overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-200">
            <h3 className="text-lg font-medium text-gray-900">Trace Details</h3>
            <p className="text-sm text-gray-600 font-mono">{selectedTraceData.trace_id}</p>
          </div>
          
          <div className="p-6">
            <div className="space-y-4">
              {selectedTraceData.spans.map((span, index) => (
                <div key={index} className="flex items-start space-x-4">
                  {/* Timeline */}
                  <div className="flex flex-col items-center">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                      span.status === 'success' ? 'bg-green-100 text-green-600' :
                      span.status === 'error' ? 'bg-red-100 text-red-600' :
                      'bg-blue-100 text-blue-600'
                    }`}>
                      {getServiceIcon(span.service)}
                    </div>
                    {index < selectedTraceData.spans.length - 1 && (
                      <div className="w-0.5 h-12 bg-gray-200 mt-2"></div>
                    )}
                  </div>
                  
                  {/* Span Details */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-2">
                      <div>
                        <h4 className="text-sm font-medium text-gray-900">{span.service}</h4>
                        <p className="text-sm text-gray-600">{span.operation}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-sm font-medium text-gray-900">
                          {formatDuration(span.duration)}
                        </p>
                        <p className="text-xs text-gray-500">
                          {new Date(span.timestamp).toLocaleTimeString()}
                        </p>
                      </div>
                    </div>
                    
                    {/* Attributes */}
                    {span.attributes && Object.keys(span.attributes).length > 0 && (
                      <div className="bg-gray-50 rounded p-3 mt-2">
                        <h5 className="text-xs font-medium text-gray-700 mb-2">Attributes</h5>
                        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                          {Object.entries(span.attributes).map(([key, value]) => (
                            <React.Fragment key={key}>
                              <dt className="text-gray-500 font-mono">{key}</dt>
                              <dd className="text-gray-900 font-mono truncate">{String(value)}</dd>
                            </React.Fragment>
                          ))}
                        </dl>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Demo Notice */}
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
        <div className="flex">
          <AlertCircle className="w-5 h-5 text-yellow-600" />
          <div className="ml-3">
            <h3 className="text-sm font-medium text-yellow-800">Demo Data</h3>
            <p className="text-sm text-yellow-700 mt-1">
              This trace viewer shows mock data for demonstration. In a real implementation, traces would be fetched from your OTEL collector's storage backend (like Jaeger, Zipkin, or your monitoring platform).
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TraceViewer;