const API_PREFIX = '/api/backend'; // All calls go through the Next.js rewrite proxy

async function request(endpoint, options = {}) {
  const url = `${API_PREFIX}${endpoint}`;
  const defaultHeaders = {
    'Content-Type': 'application/json',
  };

  const config = {
    ...options,
    headers: {
      ...defaultHeaders,
      ...options.headers,
    },
  };

  try {
    const response = await fetch(url, config);
    if (!response.ok) {
      let errorData;
      try {
        errorData = await response.json();
      } catch (e) {
        // If response is not JSON, use status text or a generic message
        errorData = { message: response.statusText || `Request failed with status ${response.status}` };
      }
      // Ensure the error thrown has a message property
      const errorMessage = errorData.message || `Server error: ${response.status}`;
      const error = new Error(errorMessage);
      error.response = response; // Attach full response if needed
      error.data = errorData;    // Attach parsed error data if available
      throw error;
    }
    // If response is OK but has no content (e.g., 204 No Content)
    if (response.status === 204) {
        return null; 
    }
    return response.json();
  } catch (error) {
    // Log the error or handle it as needed before re-throwing
    // console.error(`API request to ${url} failed:`, error.message);
    throw error; // Re-throw to be caught by the calling function
  }
}

export const apiClient = {
  uploadAudio: (payload) => {
    return request('/audio/upload', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },
  getJobStatus: (jobId) => {
    return request(`/audio/status/${jobId}`); // GET is default
  },
  // The result URL for download/audio src will still be constructed with the prefix
  // directly in the component, as it's a URL, not a data fetch, but we can provide a helper.
  getJobResultUrl: (jobId) => {
    return `${API_PREFIX}/audio/result/${jobId}`;
  }
}; 