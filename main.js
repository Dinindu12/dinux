const API_URL = "http://162.35.189.85:8000";
const app = document.querySelector("#app");
// ===== STATE =====
const state = {
  url: "",
  video: null,
  format: "bestvideo+bestaudio",
  result: null,
  loading: false,
  message: "",
  error: "",
  downloadProgress: 0,
  downloadSpeed: 0,
  downloadTotal: 0,
  downloadRemaining: 0,
  isDownloading: false,
  cancelDownload: false,
};

// ===== UTILITIES =====
function uniqueFormats(formats = []) {
  const seen = new Map();
  formats
    .filter((f) => f && f.vcodec !== "none" && f.height)
    .forEach((f) => {
      if (!seen.has(f.height)) seen.set(f.height, f);
    });
  return [...seen.values()].sort((a, b) => (b.height || 0) - (a.height || 0));
}

function durationText(seconds) {
  if (!seconds) return "Unknown";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function viewText(value) {
  if (!value) return "Unknown views";
  return new Intl.NumberFormat("en", { notation: "compact" }).format(value);
}

function sizeText(bytes) {
  if (!bytes) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let size = bytes;
  while (size >= 1024 && i < units.length - 1) {
    size /= 1024;
    i++;
  }
  return `${size.toFixed(1)} ${units[i]}`;
}

function formatSpeed(bytesPerSecond) {
  if (!bytesPerSecond || bytesPerSecond < 0) return "0 B/s";
  return sizeText(bytesPerSecond) + "/s";
}

function formatTime(seconds) {
  if (!seconds || seconds < 0 || !isFinite(seconds)) return "—";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

// ===== RENDER =====
function render() {
  const formats = uniqueFormats(state.video?.formats || []);
  const theme = document.documentElement.getAttribute("data-theme") || "light";

  app.innerHTML = `
    <div class="app">
      <header class="header">
        <div class="brand">
          <div class="brand-icon">↓</div>
          <div>
            <h1>DinuVx</h1>
            <span>Video Downloader</span>
          </div>
        </div>
        <div class="header-right">
          <button class="theme-toggle" id="theme-toggle" aria-label="Toggle theme">
            ${theme === "dark" ? "☀️" : "🌙"}
          </button>
          <div class="header-status"><span class="status-dot"></span> Online</div>
        </div>
      </header>

      <main>
        <section class="hero">
          <div class="hero-badge">⚡ Fast • Simple • Free</div>
          <h1>Download videos<br><span>your way.</span></h1>
          <p>Paste a video URL, choose your preferred quality, and download.</p>

          <form id="video-form" class="url-form">
            <div class="input-wrapper">
              <input id="video-url" type="url" value="${state.url}" placeholder="Paste video URL here..." required />
            </div>
            <button class="analyze-button" type="submit" ${state.loading ? "disabled" : ""}>
              ${state.loading ? "Analyzing…" : "Analyze"}
            </button>
          </form>

          <div class="trust-row">
            <span>🔒 No registration</span>
            <span>🕶️ Privacy focused</span>
          </div>
        </section>

        ${state.error ? `<div class="error-box">❌ ${state.error}</div>` : ""}

        ${state.loading ? `
          <div class="progress-container">
            <div class="progress-loader"><div></div></div>
            <span>${state.message || "Processing..."}</span>
          </div>
        ` : ""}

        ${state.video && !state.loading ? `
          <section class="result-section">
            <div class="video-card">
              <img class="thumbnail" src="${state.video.thumbnail || ""}" alt="${state.video.title || "Video thumbnail"}" />
              <div class="video-details">
                <h2>${state.video.title || "Untitled video"}</h2>
                <div class="video-meta">
                  <span>📺 ${state.video.channel || state.video.uploader || "Unknown channel"}</span>
                  <span>⏱ ${durationText(state.video.duration)}</span>
                  <span>👁 ${viewText(state.video.view_count)}</span>
                </div>
              </div>
            </div>

            <div class="format-section">
              <div class="section-title">📥 Select Quality</div>
              <div class="format-grid">
                ${formats.map((format) => `
                  <button
                    type="button"
                    class="format ${state.format === `${format.id}+bestaudio` ? "active" : ""}"
                    data-format="${format.id}+bestaudio"
                  >
                    <strong>${format.height}p</strong>
                    <span>${format.ext} ${format.filesize ? `• ${sizeText(format.filesize)}` : ""}</span>
                    ${format.vcodec ? `<span class="codec">${format.vcodec.split(".")[0]}</span>` : ""}
                  </button>
                `).join("")}
              </div>

              <button
                type="button"
                class="audio-format ${state.format === "bestaudio" ? "active" : ""}"
                data-format="bestaudio"
              >
                🎵 Audio Only (MP3)
              </button>
            </div>

            <div class="action-row">
              <button type="button" id="download-start" class="main-download" ${state.isDownloading ? "disabled" : ""}>
                ${state.isDownloading ? "Downloading…" : "⬇️ Start Download"}
              </button>
              <button type="button" id="reset-btn" class="reset-button">🔄 New URL</button>
            </div>

            ${state.isDownloading ? `
              <div class="download-progress">
                <div class="progress-bar-bg">
                  <div class="progress-bar-fill" style="width: ${state.downloadProgress}%"></div>
                </div>
                <div class="progress-stats">
                  <span>${state.downloadProgress.toFixed(0)}%</span>
                  <span>${sizeText(state.downloadTotal)}</span>
                  <span>${formatSpeed(state.downloadSpeed)}</span>
                  <span>⏳ ${formatTime(state.downloadRemaining)}</span>
                </div>
                <button id="cancel-download" class="cancel-button">✖ Cancel</button>
              </div>
            ` : ""}

            ${state.result && !state.isDownloading ? `
              <div class="success-card">
                <div class="success-icon">✅</div>
                <div class="success-content">
                  <strong>Download complete!</strong>
                  <span>${state.result.title || "Your file is ready"}</span>
                </div>
              </div>
            ` : ""}
          </section>
        ` : ""}

        <section class="features">
          <div class="feature"><strong>⚡ Fast</strong><span>Powered by yt-dlp</span></div>
          <div class="feature"><strong>🔒 Private</strong><span>No account required</span></div>
          <div class="feature"><strong>🎛️ Flexible</strong><span>Multiple qualities</span></div>
        </section>
      </main>

      <footer>
        <span>@2024 - 2026 All rights reserved</span>
        <span>Build with ❤️ Dinidu jaympathi</span>
      </footer>
    </div>
  `;

  // ----- Event Listeners -----

  // Theme toggle
  const toggle = document.querySelector("#theme-toggle");
  if (toggle) {
    toggle.addEventListener("click", () => {
      const current = document.documentElement.getAttribute("data-theme");
      const next = current === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("theme", next);
      render();
    });
  }

  // Analyze form
  const form = document.querySelector("#video-form");
  if (form) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const url = document.querySelector("#video-url")?.value?.trim();
      if (!url) return;

      state.url = url;
      state.error = "";
      state.result = null;
      state.loading = true;
      state.message = "Analyzing video...";
      state.isDownloading = false;
      render();

      try {
        const response = await fetch(`${API_URL}/api/info`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Unable to analyze URL");
        state.video = data;
        state.format = "bestvideo+bestaudio";
      } catch (err) {
        state.error = err.message || "Unable to analyze URL";
        state.video = null;
      } finally {
        state.loading = false;
        state.message = "";
        render();
      }
    });
  }

  // Format selection
  document.querySelectorAll("[data-format]").forEach((button) => {
    button.addEventListener("click", () => {
      state.format = button.dataset.format;
      render();
    });
  });

  // Download start (with robust error handling)
  const startBtn = document.querySelector("#download-start");
  if (startBtn) {
    startBtn.addEventListener("click", async () => {
      if (!state.video) return;
      if (state.isDownloading) return;

      state.error = "";
      state.result = null;
      state.isDownloading = true;
      state.downloadProgress = 0;
      state.downloadSpeed = 0;
      state.downloadTotal = 0;
      state.downloadRemaining = 0;
      state.cancelDownload = false;
      render();

      try {
        // 1) Prepare download
        const prepResponse = await fetch(`${API_URL}/api/download`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            url: state.url,
            format_id: state.format
          })
        });

        let prepData;
        try {
          prepData = await prepResponse.json();
        } catch (e) {
          // Response was not JSON – fallback to plain text
          const text = await prepResponse.text();
          throw new Error(`Server error (${prepResponse.status}): ${text.substring(0, 150)}`);
        }

        if (!prepResponse.ok) {
          // Now prepData should be an object with `detail`
          const detail = prepData?.detail || `HTTP ${prepResponse.status}`;
          console.error("Download error:", prepData);
          throw new Error(detail);
        }

        const downloadUrl = `${API_URL}${prepData.download_url}`;

        // 2) Fetch the actual file
        const fileResponse = await fetch(downloadUrl);
        if (!fileResponse.ok) {
          const errorText = await fileResponse.text();
          try {
            const errorJson = JSON.parse(errorText);
            throw new Error(errorJson.detail || "File not found");
          } catch {
            throw new Error(`Server error (${fileResponse.status})`);
          }
        }

        // 3) Check Content-Type – if JSON, it's an error disguised as 200
        const contentType = fileResponse.headers.get("content-type");
        if (contentType && contentType.includes("application/json")) {
          const errorData = await fileResponse.json();
          throw new Error(errorData.detail || "Unexpected JSON response");
        }

        // 4) Extract filename from Content-Disposition
        let filename = "video.mp4";
        const disposition = fileResponse.headers.get("content-disposition");
        if (disposition) {
          const match = disposition.match(/filename="(.+?)"/);
          if (match) filename = match[1];
        } else {
          // fallback: last part of URL
          const parts = downloadUrl.split("/");
          filename = parts[parts.length - 1] || "video.mp4";
        }

        // 5) Progress reading
        const contentLength = fileResponse.headers.get("content-length");
        state.downloadTotal = contentLength ? parseInt(contentLength, 10) : 0;

        const reader = fileResponse.body.getReader();
        const chunks = [];
        let loaded = 0;
        const startTime = performance.now();
        let lastTime = startTime;
        let lastLoaded = 0;

        while (true) {
          if (state.cancelDownload) {
            reader.cancel();
            throw new Error("Download cancelled");
          }

          const { done, value } = await reader.read();
          if (done) break;

          chunks.push(value);
          loaded += value.length;

          const now = performance.now();
          const elapsed = (now - lastTime) / 1000;
          if (elapsed >= 0.5) {
            const bytesDelta = loaded - lastLoaded;
            state.downloadSpeed = bytesDelta / elapsed;
            lastLoaded = loaded;
            lastTime = now;
          }

          state.downloadProgress = state.downloadTotal > 0 ? (loaded / state.downloadTotal) * 100 : 0;
          const speed = state.downloadSpeed || 1;
          const remainingBytes = state.downloadTotal - loaded;
          state.downloadRemaining = remainingBytes / speed;

          render();
        }

        // 6) Build blob and trigger download
        const blob = new Blob(chunks);
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);

        state.result = {
          title: prepData.title || "Downloaded Video",
        };
        state.isDownloading = false;
        state.downloadProgress = 100;
        render();

      } catch (err) {
        state.error = err.message || "Download failed";
        state.isDownloading = false;
        console.error("Download error caught:", err);
        render();
      }
    });
  }

  // Cancel download
  const cancelBtn = document.querySelector("#cancel-download");
  if (cancelBtn) {
    cancelBtn.addEventListener("click", () => {
      state.cancelDownload = true;
    });
  }

  // Reset
  const resetBtn = document.querySelector("#reset-btn");
  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      state.url = "";
      state.video = null;
      state.result = null;
      state.error = "";
      state.loading = false;
      state.message = "";
      state.format = "bestvideo+bestaudio";
      state.isDownloading = false;
      state.downloadProgress = 0;
      render();
    });
  }
}

// Load theme
const savedTheme = localStorage.getItem("theme") || "light";
document.documentElement.setAttribute("data-theme", savedTheme);
render();
