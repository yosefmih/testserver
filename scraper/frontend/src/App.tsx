import React, { useState } from 'react';
import { JobForm } from './components/JobForm';
import { JobList } from './components/JobList';
import './App.css';

function App() {
  const [refreshKey, setRefreshKey] = useState(0);

  const handleJobCreated = () => {
    // Trigger refresh of job list
    setRefreshKey(prev => prev + 1);
  };

  return (
    <div className="app">
      <div className="container">
        <header className="header">
          <h1>🔍 Amharic Web Scraper</h1>
          <p>Extract Amharic text from websites and store in S3</p>
        </header>

        <JobForm onJobCreated={handleJobCreated} />
        <JobList key={refreshKey} />
      </div>
    </div>
  );
}

export default App;

