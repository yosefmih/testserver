import { useState } from 'react';
import { Github, MessageSquare, Activity, Settings } from 'lucide-react';
import SlackIntegrationManager from './components/SlackIntegrationManager';
import AnalysisRequestForm from './components/AnalysisRequestForm';
import TraceViewer from './components/TraceViewer';

type TabType = 'analyze' | 'slack' | 'traces' | 'settings';

function App() {
  const [activeTab, setActiveTab] = useState<TabType>('analyze');

  const tabs = [
    { id: 'analyze' as TabType, label: 'Analyze Releases', icon: Github },
    { id: 'slack' as TabType, label: 'Slack Integration', icon: MessageSquare },
    { id: 'traces' as TabType, label: 'Trace History', icon: Activity },
    { id: 'settings' as TabType, label: 'Settings', icon: Settings },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center py-4">
            <div className="flex items-center space-x-3">
              <Github className="w-8 h-8 text-blue-600" />
              <div>
                <h1 className="text-xl font-bold text-gray-900">
                  GitHub Release Analyzer
                </h1>
                <p className="text-sm text-gray-600">
                  Distributed tracing demo with microservices
                </p>
              </div>
            </div>
            <div className="flex items-center space-x-2">
              <div className="flex items-center space-x-1 text-sm text-gray-500">
                <div className="w-2 h-2 bg-green-400 rounded-full"></div>
                <span>Services Online</span>
              </div>
            </div>
          </div>
        </div>
      </header>

      <nav className="bg-white border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex space-x-8">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center space-x-2 py-4 px-1 border-b-2 font-medium text-sm ${
                    activeTab === tab.id
                      ? 'border-blue-500 text-blue-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {activeTab === 'analyze' && (
          <div>
            <div className="mb-6">
              <h2 className="text-2xl font-bold text-gray-900">Analyze GitHub Releases</h2>
              <p className="mt-2 text-gray-600">
                Submit analysis requests and trace them through our microservice architecture.
              </p>
            </div>
            <AnalysisRequestForm />
          </div>
        )}

        {activeTab === 'slack' && (
          <div>
            <div className="mb-6">
              <h2 className="text-2xl font-bold text-gray-900">Slack Integration</h2>
              <p className="mt-2 text-gray-600">
                Configure Slack workspaces to receive breaking change notifications.
              </p>
            </div>
            <SlackIntegrationManager />
          </div>
        )}

        {activeTab === 'traces' && (
          <div>
            <div className="mb-6">
              <h2 className="text-2xl font-bold text-gray-900">Distributed Traces</h2>
              <p className="mt-2 text-gray-600">
                View traces flowing through GitHub Release Crawler → Notification Service → Slack.
              </p>
            </div>
            <TraceViewer />
          </div>
        )}

        {activeTab === 'settings' && (
          <div>
            <div className="mb-6">
              <h2 className="text-2xl font-bold text-gray-900">Service Settings</h2>
              <p className="mt-2 text-gray-600">
                Configure service endpoints and OpenTelemetry settings.
              </p>
            </div>
            <div className="bg-white rounded-lg shadow p-6">
              <h3 className="text-lg font-medium mb-4">Service Endpoints</h3>
              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-sm font-medium">GitHub Release Crawler</span>
                  <span className="text-sm text-gray-500 font-mono">http://github-release-crawler:18080</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm font-medium">Slack Notification Service</span>
                  <span className="text-sm text-gray-500 font-mono">http://slack-notification-service:3001</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm font-medium">OTEL Collector</span>
                  <span className="text-sm text-gray-500 font-mono">http://otel-collector:4318</span>
                </div>
              </div>

              <h3 className="text-lg font-medium mb-4 mt-8">Tracing Configuration</h3>
              <div className="bg-gray-50 rounded p-4">
                <code className="text-sm">
                  <div>Service: porter</div>
                  <div>Endpoint: otel-collector:4318</div>
                  <div>Exporters: honeycomb, datadog</div>
                </code>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;