import React, { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Github, Send, AlertTriangle, CheckCircle, Clock, ExternalLink } from 'lucide-react';
import axios from 'axios';

const AnalysisRequestSchema = z.object({
  githubUrl: z.string()
    .url('Must be a valid URL')
    .refine((url) => url.includes('github.com'), 'Must be a GitHub repository URL'),
  currentVersion: z.string().min(1, 'Current version is required'),
  githubToken: z.string().optional(),
  channels: z.string().optional(),
});

type AnalysisRequestFormData = z.infer<typeof AnalysisRequestSchema>;

interface AnalysisResult {
  requestId: string;
  timestamp: string;
  input: {
    githubUrl: string;
    currentVersion: string;
  };
  analysis: {
    breakingChanges: Array<{
      version: string;
      severity: 'low' | 'medium' | 'high' | 'critical';
      description: string;
      category: string;
      mitigation?: string;
    }>;
    summary: string;
    riskLevel: 'low' | 'medium' | 'high' | 'critical';
    recommendedActions: string[];
  };
}

const AnalysisRequestForm: React.FC = () => {
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [traceId, setTraceId] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors },
    watch
  } = useForm<AnalysisRequestFormData>({
    resolver: zodResolver(AnalysisRequestSchema),
    defaultValues: {
      githubUrl: 'https://github.com/microsoft/TypeScript',
      currentVersion: '5.0.0'
    }
  });

  const githubUrl = watch('githubUrl');

  const onSubmit = async (data: AnalysisRequestFormData) => {
    try {
      setSubmitting(true);
      setError(null);
      setResult(null);
      
      // Generate a trace ID for this request
      const newTraceId = `frontend-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      setTraceId(newTraceId);

      console.log('🚀 Submitting analysis request:', {
        ...data,
        traceId: newTraceId
      });

      const requestData = {
        githubUrl: data.githubUrl,
        currentVersion: data.currentVersion,
        ...(data.githubToken && { githubToken: data.githubToken }),
        ...(data.channels && { channels: data.channels.split(',').map(c => c.trim()) })
      };

      const response = await axios.post('/api/analyze', requestData, {
        headers: {
          'x-request-id': newTraceId,
          'Content-Type': 'application/json'
        },
        timeout: 120000 // 2 minutes timeout
      });

      console.log('✅ Analysis completed:', response.data);
      setResult(response.data);

    } catch (err: any) {
      console.error('❌ Analysis failed:', err);
      
      if (err.code === 'ECONNABORTED') {
        setError('Request timeout - analysis is taking longer than expected');
      } else if (err.response?.data?.error) {
        setError(err.response.data.error);
      } else if (err.response?.status === 400) {
        setError('Invalid request - please check your inputs');
      } else if (err.response?.status === 500) {
        setError('Server error - please try again later');
      } else {
        setError('Failed to connect to analysis service');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical': return 'text-red-600 bg-red-100';
      case 'high': return 'text-orange-600 bg-orange-100';
      case 'medium': return 'text-yellow-600 bg-yellow-100';
      case 'low': return 'text-green-600 bg-green-100';
      default: return 'text-gray-600 bg-gray-100';
    }
  };

  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case 'critical':
      case 'high':
        return <AlertTriangle className="w-4 h-4" />;
      case 'medium':
        return <Clock className="w-4 h-4" />;
      case 'low':
        return <CheckCircle className="w-4 h-4" />;
      default:
        return <AlertTriangle className="w-4 h-4" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Analysis Request Form */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="mb-6">
          <h3 className="text-lg font-medium text-gray-900 flex items-center">
            <Github className="w-5 h-5 mr-2" />
            Repository Analysis
          </h3>
          <p className="mt-1 text-sm text-gray-600">
            Analyze GitHub releases for breaking changes. Results will be sent to configured Slack channels.
          </p>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className="block text-sm font-medium text-gray-700">
                GitHub Repository URL *
              </label>
              <input
                {...register('githubUrl')}
                type="text"
                className="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                placeholder="https://github.com/owner/repo"
              />
              {errors.githubUrl && (
                <p className="mt-1 text-sm text-red-600">{errors.githubUrl.message}</p>
              )}
              {githubUrl && githubUrl.includes('github.com') && (
                <p className="mt-1 text-sm text-green-600 flex items-center">
                  <CheckCircle className="w-4 h-4 mr-1" />
                  Valid GitHub repository URL
                </p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">
                Current Version *
              </label>
              <input
                {...register('currentVersion')}
                type="text"
                className="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                placeholder="1.0.0"
              />
              {errors.currentVersion && (
                <p className="mt-1 text-sm text-red-600">{errors.currentVersion.message}</p>
              )}
              <p className="mt-1 text-xs text-gray-500">
                Analyze releases after this version
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">
                GitHub Token (Optional)
              </label>
              <input
                {...register('githubToken')}
                type="password"
                className="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                placeholder="ghp_xxxxxxxxxxxx"
              />
              <p className="mt-1 text-xs text-gray-500">
                For higher API rate limits
              </p>
            </div>

            <div className="sm:col-span-2">
              <label className="block text-sm font-medium text-gray-700">
                Slack Channels (Optional)
              </label>
              <input
                {...register('channels')}
                type="text"
                className="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                placeholder="#releases, #dev-team"
              />
              <p className="mt-1 text-xs text-gray-500">
                Comma-separated list of channels (overrides default)
              </p>
            </div>
          </div>

          <div className="flex justify-end pt-4">
            <button
              type="submit"
              disabled={submitting}
              className="inline-flex items-center px-6 py-3 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {submitting ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                  Analyzing...
                </>
              ) : (
                <>
                  <Send className="w-4 h-4 mr-2" />
                  Start Analysis
                </>
              )}
            </button>
          </div>
        </form>
      </div>

      {/* Trace ID Display */}
      {traceId && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <ExternalLink className="w-5 h-5 text-blue-600" />
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-blue-800">
                Distributed Trace ID
              </h3>
              <p className="text-sm text-blue-700 font-mono">
                {traceId}
              </p>
              <p className="text-xs text-blue-600 mt-1">
                Use this ID to trace the request through all microservices in your monitoring tools.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Error Display */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex">
            <AlertTriangle className="w-5 h-5 text-red-600" />
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800">Analysis Failed</h3>
              <p className="text-sm text-red-700 mt-1">{error}</p>
              {traceId && (
                <p className="text-xs text-red-600 mt-2">
                  Trace ID: {traceId}
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Results Display */}
      {result && (
        <div className="bg-white rounded-lg shadow">
          <div className="px-6 py-4 border-b border-gray-200">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-medium text-gray-900">Analysis Results</h3>
              <div className="flex items-center space-x-2">
                <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getSeverityColor(result.analysis.riskLevel)}`}>
                  {getSeverityIcon(result.analysis.riskLevel)}
                  <span className="ml-1">{result.analysis.riskLevel.toUpperCase()}</span>
                </span>
                <span className="text-xs text-gray-500">
                  {new Date(result.timestamp).toLocaleString()}
                </span>
              </div>
            </div>
          </div>

          <div className="p-6">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Summary */}
              <div className="lg:col-span-2">
                <h4 className="text-sm font-medium text-gray-900 mb-3">Summary</h4>
                <p className="text-sm text-gray-700 mb-4">{result.analysis.summary}</p>

                {/* Breaking Changes */}
                {result.analysis.breakingChanges.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium text-gray-900 mb-3">
                      Breaking Changes ({result.analysis.breakingChanges.length})
                    </h4>
                    <div className="space-y-3">
                      {result.analysis.breakingChanges.map((change, index) => (
                        <div key={index} className="border border-gray-200 rounded-lg p-4">
                          <div className="flex items-start justify-between mb-2">
                            <div className="flex items-center space-x-2">
                              <span className="text-sm font-medium text-gray-900">
                                {change.version}
                              </span>
                              <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${getSeverityColor(change.severity)}`}>
                                {change.severity}
                              </span>
                            </div>
                            <span className="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded">
                              {change.category}
                            </span>
                          </div>
                          <p className="text-sm text-gray-700 mb-2">{change.description}</p>
                          {change.mitigation && (
                            <p className="text-xs text-blue-700 bg-blue-50 p-2 rounded">
                              <strong>Mitigation:</strong> {change.mitigation}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Metadata */}
              <div>
                <h4 className="text-sm font-medium text-gray-900 mb-3">Request Details</h4>
                <dl className="space-y-2 text-sm">
                  <div>
                    <dt className="text-gray-500">Repository</dt>
                    <dd className="font-mono text-xs break-all">
                      <a href={result.input.githubUrl} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">
                        {result.input.githubUrl.replace('https://github.com/', '')}
                      </a>
                    </dd>
                  </div>
                  <div>
                    <dt className="text-gray-500">Version Range</dt>
                    <dd className="font-mono">{result.input.currentVersion} → latest</dd>
                  </div>
                  <div>
                    <dt className="text-gray-500">Request ID</dt>
                    <dd className="font-mono text-xs break-all">{result.requestId}</dd>
                  </div>
                </dl>

                {/* Recommended Actions */}
                {result.analysis.recommendedActions.length > 0 && (
                  <div className="mt-6">
                    <h4 className="text-sm font-medium text-gray-900 mb-3">Recommended Actions</h4>
                    <ul className="space-y-1 text-sm text-gray-700">
                      {result.analysis.recommendedActions.map((action, index) => (
                        <li key={index} className="flex items-start">
                          <CheckCircle className="w-4 h-4 text-green-500 mr-2 mt-0.5 flex-shrink-0" />
                          {action}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AnalysisRequestForm;