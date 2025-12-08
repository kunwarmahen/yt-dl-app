import React, { useState, useEffect } from "react";
import "./App.css";

const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:8000";

function App() {
  const [url, setUrl] = useState("");
  const [customName, setCustomName] = useState("");
  const [downloads, setDownloads] = useState({});
  const [files, setFiles] = useState([]);
  const [config, setConfig] = useState(null);
  const [showSettings, setShowSettings] = useState(false);
  const [tempPath, setTempPath] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 10;

  // Load initial data
  useEffect(() => {
    loadConfig();
    loadDownloads();
    loadFiles();

    const interval = setInterval(() => {
      loadDownloads();
      loadFiles();
    }, 2000);

    return () => clearInterval(interval);
  }, []);

  const loadConfig = async () => {
    try {
      const res = await fetch(`${API_BASE}/config`);
      const data = await res.json();
      setConfig(data);
      setTempPath(data.download_path);
      setLoading(false);
    } catch (err) {
      setError("Failed to load configuration");
      setLoading(false);
    }
  };

  const loadDownloads = async () => {
    try {
      const res = await fetch(`${API_BASE}/downloads`);
      const data = await res.json();
      setDownloads(data);
    } catch (err) {
      console.error("Failed to load downloads:", err);
    }
  };

  const loadFiles = async () => {
    try {
      const res = await fetch(`${API_BASE}/files`);
      const data = await res.json();
      console.log("Files loaded from backend:", data);
      setFiles(data);
    } catch (err) {
      console.error("Failed to load files:", err);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!url.trim()) return;

    try {
      const res = await fetch(`${API_BASE}/download`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: url.trim(),
          custom_name: customName.trim() || undefined,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setUrl("");
        setCustomName("");
        loadDownloads();
      } else {
        const err = await res.json();
        setError(err.detail || "Failed to start download");
      }
    } catch (err) {
      setError("Failed to submit download");
    }
  };

  const handleUpdateConfig = async () => {
    try {
      const res = await fetch(`${API_BASE}/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ download_path: tempPath }),
      });

      if (res.ok) {
        await loadConfig();
        setShowSettings(false);
        setError(null);
      }
    } catch (err) {
      setError("Failed to update configuration");
    }
  };

  const handleClearDownload = async (downloadId) => {
    try {
      await fetch(`${API_BASE}/downloads/${downloadId}`, {
        method: "DELETE",
      });
      loadDownloads();
    } catch (err) {
      console.error("Failed to clear download:", err);
    }
  };

  const formatBytes = (bytes) => {
    if (bytes === 0 || bytes === undefined || bytes === null) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + " " + sizes[i];
  };

  const formatTime = (timestamp) => {
    // timestamp is in seconds, convert to milliseconds for JavaScript
    const date = new Date(timestamp * 1000);
    return date.toLocaleString();
  };

  const formatISOTime = (isoString) => {
    // For ISO 8601 format strings from downloads (created_at)
    const date = new Date(isoString);
    return date.toLocaleTimeString();
  };

  const handlePlayFile = (filename) => {
    const fileUrl = `${API_BASE}/play/${encodeURIComponent(filename)}`;
    // Open in new window for streaming
    window.open(fileUrl, "_blank");
  };

  const handleDownloadFile = (filename) => {
    const fileUrl = `${API_BASE}/download-file/${encodeURIComponent(filename)}`;
    // Trigger download
    const link = document.createElement("a");
    link.href = fileUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Filter files based on search query
  const filteredFiles = files.filter((file) =>
    file.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Pagination logic
  const totalPages = Math.ceil(filteredFiles.length / itemsPerPage);
  const startIndex = (currentPage - 1) * itemsPerPage;
  const paginatedFiles = filteredFiles.slice(
    startIndex,
    startIndex + itemsPerPage
  );

  // Reset to page 1 when search query changes
  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery]);

  if (loading) {
    return <div className="container loading">Loading...</div>;
  }

  return (
    <div className="app">
      <header className="header">
        <div className="container">
          <div className="header-content">
            <div>
              <h1>🎵 Home MP3 Hub</h1>
              <p>Download YouTube audio for your collection</p>
            </div>
            <button
              className="settings-btn"
              onClick={() => setShowSettings(!showSettings)}
              title="Settings"
            >
              ⚙️
            </button>
          </div>
        </div>
      </header>

      <main className="container">
        {error && (
          <div className="alert alert-error">
            {error}
            <button onClick={() => setError(null)}>×</button>
          </div>
        )}

        {showSettings && config && (
          <div className="settings-panel">
            <h2>Settings</h2>
            <div className="form-group">
              <label>Download Directory</label>
              <input
                type="text"
                value={tempPath}
                onChange={(e) => setTempPath(e.target.value)}
                placeholder="/path/to/downloads"
              />
              <small>Location where MP3 files will be saved</small>
            </div>
            <div className="button-group">
              <button className="btn btn-primary" onClick={handleUpdateConfig}>
                Save Configuration
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => {
                  setShowSettings(false);
                  setTempPath(config.download_path);
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        <section className="section">
          <h2>Add Video</h2>
          <form onSubmit={handleSubmit} className="download-form">
            <div className="form-group">
              <label>YouTube URL</label>
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://www.youtube.com/watch?v=..."
                required
              />
            </div>

            <div className="form-group">
              <label>Custom Name (Optional)</label>
              <input
                type="text"
                value={customName}
                onChange={(e) => setCustomName(e.target.value)}
                placeholder="Leave blank to use video title"
              />
            </div>

            <button type="submit" className="btn btn-primary btn-large">
              Download MP3
            </button>
          </form>
        </section>

        {Object.keys(downloads).length > 0 && (
          <section className="section">
            <h2>Recent Downloads</h2>
            <div className="downloads-grid">
              {Object.entries(downloads)
                .sort(
                  (a, b) =>
                    new Date(b[1].created_at) - new Date(a[1].created_at)
                )
                .map(([id, dl]) => (
                  <div key={id} className={`download-card ${dl.status}`}>
                    <div className="download-status">
                      {dl.status === "downloading" && (
                        <span className="spinner"></span>
                      )}
                      {dl.status === "completed" && (
                        <span className="icon">✓</span>
                      )}
                      {dl.status === "error" && <span className="icon">✕</span>}
                      {dl.status === "queued" && (
                        <span className="icon">⏳</span>
                      )}
                    </div>

                    <div className="download-content">
                      <h3>{dl.title || "Processing..."}</h3>
                      <p className="status-text">{dl.status.toUpperCase()}</p>

                      {dl.status === "downloading" && (
                        <div className="progress-bar">
                          <div
                            className="progress-fill"
                            style={{ width: `${dl.progress}%` }}
                          ></div>
                          <span className="progress-text">{dl.progress}%</span>
                        </div>
                      )}

                      {dl.error && <p className="error-text">{dl.error}</p>}

                      <p className="time-text">
                        {formatISOTime(dl.created_at)}
                      </p>
                    </div>

                    <button
                      className="btn-clear"
                      onClick={() => handleClearDownload(id)}
                      title="Clear from list"
                    >
                      ✕
                    </button>
                  </div>
                ))}
            </div>
          </section>
        )}

        {files.length > 0 && (
          <section className="section">
            <div className="section-header">
              <h2>
                Downloaded Files ({filteredFiles.length} of {files.length})
              </h2>
              <input
                type="text"
                className="search-box"
                placeholder="🔍 Search files..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>

            {filteredFiles.length === 0 ? (
              <div className="no-results">
                <p>No files match your search "{searchQuery}"</p>
              </div>
            ) : (
              <>
                <div className="files-table">
                  <div className="table-header">
                    <div className="col-name">Filename</div>
                    <div className="col-size">Size</div>
                    <div className="col-date">Modified</div>
                    <div className="col-actions">Actions</div>
                  </div>
                  {paginatedFiles.map((file, idx) => (
                    <div key={idx} className="table-row">
                      <div className="col-name">
                        <span className="file-icon">🎵</span>
                        {file.name}
                      </div>
                      <div className="col-size">{formatBytes(file.size)}</div>
                      <div className="col-date">
                        {formatTime(file.modified)}
                      </div>
                      <div className="col-actions">
                        <button
                          className="btn-action btn-play"
                          onClick={() => handlePlayFile(file.name)}
                          title="Play"
                        >
                          ▶️
                        </button>
                        <button
                          className="btn-action btn-download"
                          onClick={() => handleDownloadFile(file.name)}
                          title="Download"
                        >
                          ⬇️
                        </button>
                      </div>
                    </div>
                  ))}
                </div>

                {totalPages > 1 && (
                  <div className="pagination">
                    <button
                      className="pagination-btn"
                      onClick={() => setCurrentPage(currentPage - 1)}
                      disabled={currentPage === 1}
                    >
                      ← Previous
                    </button>

                    <div className="pagination-info">
                      Page {currentPage} of {totalPages}
                    </div>

                    <button
                      className="pagination-btn"
                      onClick={() => setCurrentPage(currentPage + 1)}
                      disabled={currentPage === totalPages}
                    >
                      Next →
                    </button>
                  </div>
                )}
              </>
            )}
          </section>
        )}

        {Object.keys(downloads).length === 0 && files.length === 0 && (
          <section className="section empty-state">
            <p>Share a YouTube link above to get started!</p>
          </section>
        )}
      </main>

      <footer className="footer">
        <p>Running on your local network • No tracking, no ads</p>
      </footer>
    </div>
  );
}

export default App;
