import React, { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Plus, MessageSquare, TestTube, CheckCircle, XCircle, AlertCircle } from 'lucide-react';
import axios from 'axios';

const SlackIntegrationSchema = z.object({
  workspace_name: z.string().min(1, 'Workspace name is required'),
  workspace_id: z.string().min(1, 'Workspace ID is required'),
  bot_token: z.string().min(1, 'Bot token is required').startsWith('xoxb-', 'Bot token must start with xoxb-'),
  default_channel: z.string().min(1, 'Default channel is required').startsWith('#', 'Channel must start with #'),
});

type SlackIntegrationForm = z.infer<typeof SlackIntegrationSchema>;

interface SlackIntegration {
  id: number;
  workspace_id: string;
  workspace_name: string;
  bot_token: string;
  default_channel: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

const SlackIntegrationManager: React.FC = () => {
  const [integrations, setIntegrations] = useState<SlackIntegration[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset
  } = useForm<SlackIntegrationForm>({
    resolver: zodResolver(SlackIntegrationSchema),
  });

  const fetchIntegrations = async () => {
    try {
      setError(null);
      const response = await axios.get('/api/notifications/integrations');
      if (response.data.success) {
        setIntegrations(response.data.integrations);
      } else {
        setError('Failed to load integrations');
      }
    } catch (err) {
      setError('Failed to connect to notification service');
      console.error('Error fetching integrations:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchIntegrations();
  }, []);

  const onSubmit = async (data: SlackIntegrationForm) => {
    try {
      setSubmitting(true);
      setError(null);
      setSuccess(null);

      const response = await axios.post('/api/notifications/integrations', data);
      
      if (response.data.success) {
        setSuccess(`Integration "${data.workspace_name}" ${response.data.connection_test ? 'created and tested successfully' : 'created (connection test failed)'}`);
        setShowForm(false);
        reset();
        await fetchIntegrations();
      } else {
        setError(response.data.error || 'Failed to create integration');
      }
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to create integration');
    } finally {
      setSubmitting(false);
    }
  };

  const testSlackConnection = async (integration: SlackIntegration) => {
    try {
      setTestingId(integration.id);
      setError(null);
      setSuccess(null);

      const response = await axios.post('/api/notifications/test-message', {
        channel: integration.default_channel,
        workspace_id: integration.workspace_id
      });

      if (response.data.success) {
        setSuccess(`Test message sent successfully to ${integration.default_channel}!`);
      } else {
        setError(`Test failed: ${response.data.error}`);
      }
    } catch (err: any) {
      setError(err.response?.data?.error || 'Test message failed');
    } finally {
      setTestingId(null);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Status Messages */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center space-x-2">
          <XCircle className="w-5 h-5 text-red-600" />
          <span className="text-red-800">{error}</span>
        </div>
      )}

      {success && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-4 flex items-center space-x-2">
          <CheckCircle className="w-5 h-5 text-green-600" />
          <span className="text-green-800">{success}</span>
        </div>
      )}

      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h3 className="text-lg font-medium text-gray-900">Slack Workspaces</h3>
          <p className="text-sm text-gray-600">
            {integrations.length} integration{integrations.length !== 1 ? 's' : ''} configured
          </p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
        >
          <Plus className="w-4 h-4 mr-2" />
          Add Integration
        </button>
      </div>

      {/* Add Integration Form */}
      {showForm && (
        <div className="bg-white rounded-lg shadow p-6 border">
          <h4 className="text-lg font-medium mb-4">Add Slack Integration</h4>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Workspace Name
                </label>
                <input
                  {...register('workspace_name')}
                  type="text"
                  className="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                  placeholder="My Team Workspace"
                />
                {errors.workspace_name && (
                  <p className="mt-1 text-sm text-red-600">{errors.workspace_name.message}</p>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Workspace ID
                </label>
                <input
                  {...register('workspace_id')}
                  type="text"
                  className="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                  placeholder="T1234567890"
                />
                {errors.workspace_id && (
                  <p className="mt-1 text-sm text-red-600">{errors.workspace_id.message}</p>
                )}
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">
                Bot Token
              </label>
              <input
                {...register('bot_token')}
                type="password"
                className="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                placeholder="xoxb-your-bot-token-here"
              />
              {errors.bot_token && (
                <p className="mt-1 text-sm text-red-600">{errors.bot_token.message}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">
                Default Channel
              </label>
              <input
                {...register('default_channel')}
                type="text"
                className="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                placeholder="#releases"
              />
              {errors.default_channel && (
                <p className="mt-1 text-sm text-red-600">{errors.default_channel.message}</p>
              )}
            </div>

            <div className="flex justify-end space-x-3 pt-4">
              <button
                type="button"
                onClick={() => {
                  setShowForm(false);
                  reset();
                }}
                className="px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
              >
                {submitting ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                    Creating...
                  </>
                ) : (
                  'Create Integration'
                )}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Integration List */}
      {integrations.length === 0 && !showForm && (
        <div className="text-center py-12">
          <MessageSquare className="mx-auto h-12 w-12 text-gray-400" />
          <h3 className="mt-2 text-sm font-medium text-gray-900">No Slack integrations</h3>
          <p className="mt-1 text-sm text-gray-500">
            Get started by adding your first Slack workspace.
          </p>
          <div className="mt-6">
            <button
              onClick={() => setShowForm(true)}
              className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700"
            >
              <Plus className="w-4 h-4 mr-2" />
              Add Integration
            </button>
          </div>
        </div>
      )}

      {integrations.length > 0 && (
        <div className="bg-white shadow rounded-lg overflow-hidden">
          <ul className="divide-y divide-gray-200">
            {integrations.map((integration) => (
              <li key={integration.id} className="p-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <div className="flex-shrink-0">
                      <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
                        <MessageSquare className="w-6 h-6 text-purple-600" />
                      </div>
                    </div>
                    <div className="ml-4">
                      <div className="flex items-center space-x-2">
                        <h4 className="text-sm font-medium text-gray-900">
                          {integration.workspace_name}
                        </h4>
                        {integration.is_active ? (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                            Active
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">
                            Inactive
                          </span>
                        )}
                      </div>
                      <div className="text-sm text-gray-500">
                        {integration.default_channel} • ID: {integration.workspace_id}
                      </div>
                      <div className="text-xs text-gray-400">
                        Created {new Date(integration.created_at).toLocaleDateString()}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    <button
                      onClick={() => testSlackConnection(integration)}
                      disabled={testingId === integration.id}
                      className="inline-flex items-center px-3 py-2 border border-gray-300 shadow-sm text-sm leading-4 font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
                    >
                      {testingId === integration.id ? (
                        <>
                          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-gray-600 mr-2"></div>
                          Testing...
                        </>
                      ) : (
                        <>
                          <TestTube className="w-4 h-4 mr-2" />
                          Test
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Instructions */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex">
          <AlertCircle className="w-5 h-5 text-blue-600" />
          <div className="ml-3">
            <h3 className="text-sm font-medium text-blue-800">Setup Instructions</h3>
            <div className="mt-2 text-sm text-blue-700">
              <ol className="list-decimal list-inside space-y-1">
                <li>Create a Slack app at api.slack.com</li>
                <li>Add bot token scopes: chat:write, channels:read</li>
                <li>Install the app to your workspace</li>
                <li>Copy the Bot User OAuth Token (starts with xoxb-)</li>
                <li>Invite the bot to your desired channel</li>
              </ol>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SlackIntegrationManager;