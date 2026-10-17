/**
 * Tablo Classic UI - Single-Page Application Client Logic
 */

class TabloApp {
  constructor() {
    this.shows = [];
    this.currentCategory = 'all';
    this.searchQuery = '';
    this.sortBy = 'recent';
    this.currentShow = null;
    this.currentEpisodes = [];
    this.selectedEpisodeIds = new Set();
    this.hlsInstance = null;
    this.currentWatchEpisodeId = null;
    this.isSyncing = false;
    this.viewMode = localStorage.getItem('tablo_view_mode') || 'wide';

    // Guide & Scheduled Series state
    this.currentTab = 'recordings';
    this.scheduledSeries = [];
    this.scheduledFilter = 'all';
    this.scheduledSearchQuery = '';
    this.guideShows = [];
    this.guideCategory = 'all';
    this.guideRule = '';
    this.guideHighlight = null;
    this.guideSearchQuery = '';
    this.guideSort = 'title';
    this.currentGuideSeries = null;
    this.guideSearchTimeout = null;
    this.bufferTarget = parseInt(localStorage.getItem('tablo_buffer_target') || '8', 10);
    this.playerBufferTimer = null;

    // Live TV & EPG Guide state
    this.liveChannels = [];
    this.epgData = null;
    this.epgCategory = 'ota';
    this.epgHours = 6;
    this.epgStartOffset = 0;
    this.liveSearchQuery = '';
    this.currentStreamSessionId = null; // backend transcode session for the open player (recording or live)
    this.videoBufferHandler = null;
    this.currentLiveChannelId = null;
    this.liveSearchTimeout = null;
  }

  async init() {
    this.setViewMode(this.viewMode);
    await this.checkAuthStatus();
    await this.fetchStorage();
    await this.loadShows();
    this.loadScheduledSeries();
    this.loadGuideShows();
    this.startLiveClock();
    this.loadLiveEpg();
    this.checkTuners();

    // Stop the backend FFmpeg session if the tab is closed or navigated away mid-playback
    window.addEventListener('pagehide', () => this.stopCurrentStream({ keepalive: true }));

    // Poll for background sync updates & active downloads
    setInterval(() => {
      this.pollStatus();
      if (this.currentTab === 'live') {
        this.checkTuners();
      }
    }, 5000);
  }

  switchTab(tab) {
    this.currentTab = tab;
    const tabs = ['recordings', 'scheduled', 'guide', 'live'];
    tabs.forEach(t => {
      const btn = document.getElementById(`tabBtn${t.charAt(0).toUpperCase() + t.slice(1)}`);
      const view = document.getElementById(`view${t.charAt(0).toUpperCase() + t.slice(1)}`);
      if (btn) {
        if (t === tab) btn.classList.add('active');
        else btn.classList.remove('active');
      }
      if (view) {
        view.style.display = (t === tab) ? 'block' : 'none';
      }
    });

    if (tab === 'scheduled') {
      this.loadScheduledSeries();
    } else if (tab === 'guide') {
      this.loadGuideShows();
    } else if (tab === 'live') {
      this.loadLiveEpg();
      this.checkTuners();
    }
  }

  setViewMode(mode) {
    this.viewMode = mode;
    localStorage.setItem('tablo_view_mode', mode);
    const grid = document.getElementById('posterGrid');
    const btnWide = document.getElementById('btnViewWide');
    const btnPortrait = document.getElementById('btnViewPortrait');

    if (grid) {
      if (mode === 'portrait') {
        grid.classList.add('view-portrait');
      } else {
        grid.classList.remove('view-portrait');
      }
    }

    if (btnWide && btnPortrait) {
      if (mode === 'portrait') {
        btnPortrait.classList.add('active');
        btnWide.classList.remove('active');
      } else {
        btnWide.classList.add('active');
        btnPortrait.classList.remove('active');
      }
    }
  }

  getImageUrl(url) {
    if (!url || url.includes('placeholder')) return '/static/placeholder.svg';
    return url.includes('?') ? `${url}&v=2` : `${url}?v=2`;
  }

  setBufferTarget(val) {
    this.bufferTarget = parseInt(val, 10) || 8;
    localStorage.setItem('tablo_buffer_target', this.bufferTarget);
    this.showToast(`Buffer target set to ${this.bufferTarget} seconds`, 'info');
  }

  // --- Toast Notifications ---
  showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
      <span>${message}</span>
    `;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  // --- API Requests ---
  async api(endpoint, options = {}) {
    try {
      const res = await fetch(endpoint, {
        headers: { 'Content-Type': 'application/json' },
        ...options
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(errorData.detail || `Request failed with status ${res.status}`);
      }
      return await res.json();
    } catch (err) {
      console.error(`API Error on ${endpoint}:`, err);
      throw err;
    }
  }

  // --- Auth & Hardware Status ---
  async checkAuthStatus() {
    try {
      const status = await this.api('/api/auth/status');
      if (status.active_device) {
        document.getElementById('deviceName').textContent = status.active_device.name;
      }
      if (status.is_syncing) {
        this.setSyncingState(true);
      }
    } catch (err) {
      console.warn('Auth status check error:', err);
    }
  }

  async fetchStorage() {
    try {
      const storage = await this.api('/api/storage');
      if (storage.connected) {
        const usedText = `${storage.used_gb > 1000 ? (storage.used_gb / 1024).toFixed(1) + ' TB' : storage.used_gb + ' GB'} used`;
        const freeText = `${storage.free_gb > 1000 ? (storage.free_gb / 1024).toFixed(1) + ' TB' : storage.free_gb + ' GB'} free`;
        document.getElementById('storageUsedText').textContent = usedText;
        document.getElementById('storageFreeText').textContent = freeText;
        document.getElementById('storageProgressFill').style.width = `${Math.min(storage.percent_used, 100)}%`;
      } else {
        document.getElementById('storageUsedText').textContent = 'Storage unavailable';
      }
    } catch (err) {
      console.warn('Storage fetch notice:', err);
    }
  }

  // --- Shows & Grid Loading ---
  async loadShows() {
    const grid = document.getElementById('posterGrid');
    try {
      const params = new URLSearchParams();
      if (this.currentCategory !== 'all') params.append('category', this.currentCategory);
      if (this.searchQuery.trim()) params.append('search', this.searchQuery.trim());
      params.append('sort', this.sortBy);

      const res = await this.api(`/api/shows?${params.toString()}`);
      this.shows = res.shows || [];
      const badge = document.getElementById('recordingsTabBadge');
      if (badge) badge.textContent = this.shows.length;
      this.renderGrid();
      this.setViewMode(this.viewMode);
    } catch (err) {
      grid.innerHTML = `
        <div style="grid-column: 1 / -1; padding: 80px 0; text-align: center;">
          <p style="color:var(--accent-rose); font-size:1.1rem; font-weight:600; margin-bottom:12px;">Failed to load shows from Tablo</p>
          <button class="btn btn-ghost" onclick="app.loadShows()">Try Again</button>
        </div>
      `;
    }
  }

  renderGrid() {
    const grid = document.getElementById('posterGrid');
    if (!this.shows || this.shows.length === 0) {
      grid.innerHTML = `
        <div style="grid-column: 1 / -1; padding: 100px 0; text-align: center;">
          <h3 style="font-size:1.3rem; font-weight:700; color:#fff; margin-bottom:8px;">No Recordings Found</h3>
          <p style="color:var(--text-muted); font-size:0.9rem;">
            ${this.searchQuery ? `No recordings match "${this.searchQuery}"` : 'Your Tablo hard drive does not have any saved recordings for this filter.'}
          </p>
        </div>
      `;
      return;
    }

    grid.innerHTML = this.shows.map(show => {
      const epLabel = show.episode_count === 1 ? '1 Episode' : `${show.episode_count} Episodes`;
      const hasUnwatched = show.unwatched_count > 0;
      const formattedDate = this.formatDate(show.latest_recording_date);

      const rawCover = show.cover_url || show.backdrop_url;
      const posterContent = rawCover
        ? `<img class="poster-img" src="${this.getImageUrl(rawCover)}" alt="${this.escapeHtml(show.title)}" loading="lazy" onerror="this.parentElement.innerHTML = app.renderFallbackPoster('${this.escapeHtml(show.title)}')">`
        : this.renderFallbackPoster(show.title);

      return `
        <div class="show-card" onclick="app.openDrawer('${this.escapeHtml(show.id)}')">
          <div class="poster-media">
            ${posterContent}
            <div class="episode-pill-badge">
              ${hasUnwatched ? '<span class="unwatched-dot"></span>' : ''}
              <span>${show.episode_count}</span>
            </div>
          </div>
          <div class="show-meta">
            <h3 class="show-title" title="${this.escapeHtml(show.title)}">${this.escapeHtml(show.title)}</h3>
            <span class="show-date">${formattedDate ? `Recorded ${formattedDate}` : ''}</span>
          </div>
        </div>
      `;
    }).join('');
  }

  renderFallbackPoster(title) {
    return `
      <div class="fallback-poster">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" style="color:rgba(56,189,248,0.5)">
          <rect width="20" height="15" x="2" y="7" rx="2" ry="2"/>
          <polyline points="17 2 12 7 7 2"/>
        </svg>
        <span class="fallback-title">${this.escapeHtml(title)}</span>
      </div>
    `;
  }

  // --- Filtering & Sorting ---
  setCategory(category, buttonEl) {
    this.currentCategory = category;
    document.querySelectorAll('.filter-pills .pill-btn').forEach(b => b.classList.remove('active'));
    if (buttonEl) buttonEl.classList.add('active');
    this.loadShows();
  }

  onSearchInput(val) {
    this.searchQuery = val;
    // Debounce load
    clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => this.loadShows(), 180);
  }

  onSortChange(val) {
    this.sortBy = val;
    this.loadShows();
  }

  // --- Episode Drawer ---
  async openDrawer(showId) {
    try {
      const res = await this.api(`/api/shows/episodes?show_id=${encodeURIComponent(showId)}`);
      this.currentShow = res.show;
      this.currentEpisodes = res.episodes || [];
      this.selectedEpisodeIds.clear();

      // Populate header info
      document.getElementById('drawerShowTitle').textContent = this.currentShow.title;
      document.getElementById('drawerTotalEpisodes').textContent = `${this.currentShow.episode_count} Episodes`;
      document.getElementById('drawerUnwatchedCount').textContent = `${this.currentShow.unwatched_count} Unwatched`;
      document.getElementById('drawerCategory').textContent = this.currentShow.category ? this.currentShow.category.toUpperCase() : 'TV SHOW';
      document.getElementById('drawerShowDesc').textContent = this.currentShow.description || 'No description available for this series.';

      const posterImg = document.getElementById('drawerPosterImg');
      if (this.currentShow.cover_url) {
        posterImg.src = this.getImageUrl(this.currentShow.cover_url);
        posterImg.style.display = 'block';
      } else {
        posterImg.style.display = 'none';
      }

      this.updateBulkUI();
      this.renderEpisodesList();

      // Show drawer
      document.getElementById('drawerBackdrop').classList.add('active');
      document.getElementById('drawerPanel').classList.add('active');
      document.body.style.overflow = 'hidden';
    } catch (err) {
      this.showToast(`Failed opening show: ${err.message}`, 'error');
    }
  }

  closeDrawer() {
    document.getElementById('drawerBackdrop').classList.remove('active');
    document.getElementById('drawerPanel').classList.remove('active');
    document.body.style.overflow = '';
    this.currentShow = null;
    this.currentEpisodes = [];
    this.selectedEpisodeIds.clear();
  }

  renderEpisodesList() {
    const listEl = document.getElementById('drawerEpisodesList');
    if (!this.currentEpisodes || this.currentEpisodes.length === 0) {
      listEl.innerHTML = `<p style="color:var(--text-muted); text-align:center; padding:40px 0;">No episodes remaining.</p>`;
      return;
    }

    listEl.innerHTML = this.currentEpisodes.map(ep => {
      const sNum = ep.season_number > 0 ? `S${String(ep.season_number).padStart(2, '0')}` : '';
      const epNumVal = ep.episode_number || ep.number || 0;
      const eNum = epNumVal > 0 ? `E${String(epNumVal).padStart(2, '0')}` : '';
      const seBadge = (sNum && eNum) ? `${sNum} ${eNum}` : (sNum || eNum || 'EP');

      const durationMins = ep.duration ? `${Math.round(ep.duration / 60)} min` : '';
      const airDate = this.formatDate(ep.air_date);
      const isUnwatched = ep.status !== 'Watched';
      const isSelected = this.selectedEpisodeIds.has(ep.id);

      let epTitle = ep.title ? ep.title.trim() : '';
      if (!epTitle || epTitle === 'Episode') {
        epTitle = epNumVal > 0 ? `Episode ${epNumVal}` : (airDate ? `Episode (${airDate})` : 'Episode');
      }

      const isFailed = ep.recording_state === 'failed';
      const actualSecs = ep.actual_duration || 0;
      const actualMins = Math.round(actualSecs / 60);
      let statusBadgeHtml = `<span class="badge-status ${isUnwatched ? 'unwatched' : 'watched'}">${isUnwatched ? 'Unwatched' : 'Watched'}</span>`;

      if (isFailed) {
        const errDetail = ep.recording_error?.details === 'weak_signal' ? 'Weak Signal' : 'Signal Lost';
        if (actualMins > 0) {
          statusBadgeHtml = `<span class="badge-status partial" title="Interrupted broadcast: antenna lost signal after ${actualMins} min (${ep.recording_error?.details || 'error'}).">⚠️ Partial (${actualMins} min) • ${errDetail}</span>`;
        } else {
          statusBadgeHtml = `<span class="badge-status failed" title="Failed to tune: antenna signal dropped (${ep.recording_error?.details || 'error'}).">⚠️ Failed (${actualSecs}s) • ${errDetail}</span>`;
        }
      }

      const metaDurationText = isFailed 
        ? (actualMins > 0 ? `Captured ${actualMins} of ${Math.round((ep.duration || 0) / 60)} min` : '0 min captured')
        : (ep.duration ? `${Math.round(ep.duration / 60)} min` : '');

      return `
        <div class="episode-row ${isFailed ? 'row-failed' : ''}" id="epRow_${ep.id}">
          <input type="checkbox" class="episode-checkbox" ${isSelected ? 'checked' : ''} onchange="app.toggleEpisodeSelect('${ep.id}', this.checked)">
          <div class="episode-main">
            <div class="episode-badges-line">
              <span class="badge-se">${seBadge}</span>
              ${statusBadgeHtml}
              ${ep.network ? `<span style="font-size:0.75rem; color:var(--text-dim);">${this.escapeHtml(ep.network)}</span>` : ''}
            </div>
            <div class="episode-title" title="${this.escapeHtml(epTitle)}">${this.escapeHtml(epTitle)}</div>
            <div class="episode-meta-text">
              ${airDate ? `Aired ${airDate}` : ''} ${metaDurationText ? `• ${metaDurationText}` : ''}
            </div>
          </div>
          <div class="episode-actions">
            <button class="btn btn-ghost btn-sm" onclick="app.watchEpisode('${ep.id}', '${this.escapeHtml(epTitle)}')" title="Watch directly in browser">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
              <span>Watch</span>
            </button>
            <button class="btn btn-ghost btn-sm" onclick="app.openInVlc('${ep.id}')" title="Download .m3u playlist file to stream in VLC / external player">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polygon points="10 8 16 12 10 16 10 8"/></svg>
              <span>VLC</span>
            </button>
            <button class="btn btn-ghost btn-sm" onclick="app.exportEpisode('${ep.id}')" title="Download full MP4 video file to your computer">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>
              <span>Export MP4</span>
            </button>
            <button class="btn btn-ghost btn-sm" style="color:var(--accent-rose);" onclick="app.deleteEpisode('${ep.id}')" title="Delete from Tablo Hard Drive">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            </button>
          </div>
        </div>
      `;
    }).join('');
  }

  // --- Bulk Selection & Actions ---
  toggleEpisodeSelect(epId, isChecked) {
    if (isChecked) {
      this.selectedEpisodeIds.add(epId);
    } else {
      this.selectedEpisodeIds.delete(epId);
    }
    this.updateBulkUI();
  }

  toggleSelectAll(isChecked) {
    this.selectedEpisodeIds.clear();
    if (isChecked) {
      this.currentEpisodes.forEach(ep => this.selectedEpisodeIds.add(ep.id));
    }
    this.renderEpisodesList();
    this.updateBulkUI();
  }

  updateBulkUI() {
    const count = this.selectedEpisodeIds.size;
    const btnDelete = document.getElementById('btnDeleteSelected');
    const countNum = document.getElementById('selectedCountNum');
    const countText = document.getElementById('selectedCountText');
    const selectAllBox = document.getElementById('selectAllCheckbox');

    if (count > 0) {
      btnDelete.style.display = 'inline-flex';
      countNum.textContent = count;
      countText.textContent = `(${count} selected)`;
    } else {
      btnDelete.style.display = 'none';
      countText.textContent = '';
    }

    selectAllBox.checked = count > 0 && count === this.currentEpisodes.length;
  }

  async deleteEpisode(episodeId) {
    if (!confirm('Are you sure you want to delete this recording from your Tablo?')) return;
    try {
      const res = await this.api(`/api/episodes/${episodeId}`, { method: 'DELETE' });
      this.showToast('Episode deleted successfully', 'success');

      // Remove from drawer list
      this.currentEpisodes = this.currentEpisodes.filter(e => e.id !== episodeId);
      this.selectedEpisodeIds.delete(episodeId);

      // Decrement stats
      if (res.show) {
        this.currentShow = res.show;
        document.getElementById('drawerTotalEpisodes').textContent = `${res.show.episode_count} Episodes`;
        document.getElementById('drawerUnwatchedCount').textContent = `${res.show.unwatched_count} Unwatched`;
      }
      this.renderEpisodesList();
      this.updateBulkUI();

      // Refresh background grid data without reloading everything
      this.loadShows();
      this.fetchStorage();
    } catch (err) {
      this.showToast(`Delete failed: ${err.message}`, 'error');
    }
  }

  async deleteSelectedEpisodes() {
    const count = this.selectedEpisodeIds.size;
    if (count === 0) return;
    if (!confirm(`Delete ${count} selected episode(s) permanently from Tablo?`)) return;

    try {
      const ids = Array.from(this.selectedEpisodeIds);
      const res = await this.api('/api/episodes/bulk_delete', {
        method: 'POST',
        body: JSON.stringify({ episode_ids: ids })
      });

      this.showToast(`Deleted ${res.deleted_count} episode(s)`, 'success');
      if (res.errors && res.errors.length) {
        this.showToast(`${res.errors.length} episode(s) could not be deleted: ${res.errors[0]}`, 'error');
      }
      // Only drop rows the server confirmed; failed ones stay listed and selected
      const deletedIds = new Set(res.deleted_ids || []);
      this.currentEpisodes = this.currentEpisodes.filter(e => !deletedIds.has(e.id));
      deletedIds.forEach(id => this.selectedEpisodeIds.delete(id));

      this.renderEpisodesList();
      this.updateBulkUI();
      this.loadShows();
      this.fetchStorage();
    } catch (err) {
      this.showToast(`Bulk delete failed: ${err.message}`, 'error');
    }
  }

  async deleteWatchedEpisodes() {
    if (!this.currentShow) return;
    const watched = this.currentEpisodes.filter(e => e.status === 'Watched');
    if (watched.length === 0) {
      this.showToast('No watched episodes to delete in this show.', 'info');
      return;
    }

    if (!confirm(`Delete all ${watched.length} watched episode(s) for "${this.currentShow.title}"?`)) return;

    try {
      const res = await this.api(`/api/shows/delete_watched?show_id=${encodeURIComponent(this.currentShow.id)}`, { method: 'POST' });
      this.showToast(`Deleted ${res.deleted_count} watched episode(s)`, 'success');
      if (res.errors && res.errors.length) {
        this.showToast(`${res.errors.length} episode(s) could not be deleted: ${res.errors[0]}`, 'error');
      }

      const deletedIds = new Set(res.deleted_ids || []);
      this.currentEpisodes = this.currentEpisodes.filter(e => !deletedIds.has(e.id));
      this.selectedEpisodeIds.clear();

      if (res.show) {
        this.currentShow = res.show;
        document.getElementById('drawerTotalEpisodes').textContent = `${res.show.episode_count} Episodes`;
        document.getElementById('drawerUnwatchedCount').textContent = `${res.show.unwatched_count} Unwatched`;
      }

      this.renderEpisodesList();
      this.updateBulkUI();
      this.loadShows();
      this.fetchStorage();
    } catch (err) {
      this.showToast(`Delete watched failed: ${err.message}`, 'error');
    }
  }

  // --- Playback & Video Player ---
  async watchEpisode(episodeId, title) {
    this.currentWatchEpisodeId = episodeId;
    this.currentLiveChannelId = null;
    const modal = document.getElementById('playerModal');
    document.getElementById('playerTitle').textContent = title;
    modal.classList.add('active');

    // Sync buffer selector dropdown
    const bufSelect = document.getElementById('playerBufferSelect');
    if (bufSelect) bufSelect.value = String(this.bufferTarget);

    const targetSeconds = this.bufferTarget || 8;
    document.getElementById('playerSubtitle').innerHTML = `<span style="color:#fbbf24; font-weight:600;">⏳ Starting transcoder & buffering (${targetSeconds}s target)...</span>`;

    // Release any stream still running from a previous play
    this.stopCurrentStream();

    try {
      const res = await this.api(`/api/episodes/${episodeId}/watch?transcode=true`, { method: 'POST' });
      this.currentStreamSessionId = res.session_id;

      this.startHlsPlayback(res.stream_url, {
        bufferingLabel: 'Pre-buffering',
        playingLabel: '🟢 Smooth Playback',
        steadyLabel: 'Live H.264 Transcode',
        fallbackMs: 7000
      });
    } catch (err) {
      this.showToast(`Playback start error: ${err.message}`, 'error');
      document.getElementById('playerSubtitle').textContent = 'Playback failed. Try "Open in VLC".';
    }
  }

  // Shared HLS.js setup for recordings and live TV: pre-buffers to the target, then plays
  startHlsPlayback(streamUrl, { bufferingLabel, playingLabel, steadyLabel, fallbackMs }) {
    const video = document.getElementById('videoElement');
    const targetSeconds = this.bufferTarget || 8;
    this.teardownHls();

    if (Hls.isSupported()) {
      const hls = new Hls({
        enableWorker: true,
        lowLatencyMode: false, // Turn off low latency to prioritize smooth deep buffering
        backBufferLength: 90,
        maxBufferLength: 60, // Keep downloading fragments up to 60s ahead
        maxMaxBufferLength: 180, // Allow up to 3 minutes of buffer
        maxBufferSize: 80 * 1000 * 1000, // 80 MB
        startFragPrefetch: true,
        maxBufferHole: 0.5,
        highBufferWatchdogPeriod: 2
      });

      let hasStartedPlayback = false;

      const checkBuffer = () => {
        let bufferedAhead = 0;
        for (let i = 0; i < video.buffered.length; i++) {
          const start = video.buffered.start(i);
          const end = video.buffered.end(i);
          if (start <= video.currentTime && video.currentTime <= end) {
            bufferedAhead = Math.round(end - video.currentTime);
            break;
          } else if (video.currentTime === 0 && video.buffered.length > 0) {
            bufferedAhead = Math.round(end);
            break;
          }
        }

        const subtitle = document.getElementById('playerSubtitle');
        if (!hasStartedPlayback) {
          if (subtitle) {
            subtitle.innerHTML = `<span style="color:#fbbf24; font-weight:600;">⏳ ${bufferingLabel}: ${bufferedAhead}s / ${targetSeconds}s...</span>`;
          }
          if (bufferedAhead >= targetSeconds) {
            hasStartedPlayback = true;
            if (subtitle) {
              subtitle.innerHTML = `<span style="color:#10b981; font-weight:600;">${playingLabel}</span> • <span style="color:#38bdf8;">Buffer: ${bufferedAhead}s</span>`;
            }
            video.play().catch(e => console.log('Autoplay deferred:', e));
          }
        } else if (subtitle) {
          const bufferColor = bufferedAhead >= 10 ? '#10b981' : (bufferedAhead >= 4 ? '#38bdf8' : '#fbbf24');
          subtitle.innerHTML = `${steadyLabel} • <span style="color:${bufferColor}; font-weight:600;">Buffer: ${bufferedAhead}s</span>`;
        }
      };

      hls.loadSource(streamUrl);
      hls.attachMedia(video);
      video.pause();

      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        this.playerBufferTimer = setInterval(checkBuffer, 250);

        // Safety fallback: if target not reached in time, begin playback anyway
        setTimeout(() => {
          if (!hasStartedPlayback && this.hlsInstance === hls) {
            hasStartedPlayback = true;
            video.play().catch(e => console.log('Fallback play:', e));
          }
        }, fallbackMs);
      });

      hls.on(Hls.Events.FRAG_BUFFERED, checkBuffer);
      video.addEventListener('timeupdate', checkBuffer);
      video.addEventListener('progress', checkBuffer);
      this.videoBufferHandler = checkBuffer;

      hls.on(Hls.Events.ERROR, (event, data) => {
        if (data.fatal) {
          console.warn('HLS fatal error, recovering:', data.type);
          switch (data.type) {
            case Hls.ErrorTypes.NETWORK_ERROR:
              hls.startLoad();
              break;
            case Hls.ErrorTypes.MEDIA_ERROR:
              hls.recoverMediaError();
              break;
            default:
              hls.destroy();
              break;
          }
        }
      });
      this.hlsInstance = hls;
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      // Native HLS on Safari
      video.src = streamUrl;
      video.play();
    }
  }

  // Destroy the HLS.js instance, buffer timer, and video listeners from the previous play
  teardownHls() {
    if (this.playerBufferTimer) {
      clearInterval(this.playerBufferTimer);
      this.playerBufferTimer = null;
    }
    const video = document.getElementById('videoElement');
    if (this.videoBufferHandler) {
      video.removeEventListener('timeupdate', this.videoBufferHandler);
      video.removeEventListener('progress', this.videoBufferHandler);
      this.videoBufferHandler = null;
    }
    if (this.hlsInstance) {
      this.hlsInstance.destroy();
      this.hlsInstance = null;
    }
  }

  // Tell the backend to kill the FFmpeg transcode (and release the tuner for live TV)
  stopCurrentStream({ keepalive = false } = {}) {
    const sessionId = this.currentStreamSessionId;
    if (!sessionId) return;
    this.currentStreamSessionId = null;
    fetch('/api/live/stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
      keepalive
    }).catch(e => console.warn('Stream session stop notification:', e));
  }

  closePlayer() {
    this.teardownHls();
    const modal = document.getElementById('playerModal');
    const video = document.getElementById('videoElement');
    video.pause();
    video.removeAttribute('src');
    video.load();
    modal.classList.remove('active');

    this.stopCurrentStream();
    if (this.currentLiveChannelId) {
      this.currentLiveChannelId = null;
      setTimeout(() => this.checkTuners(), 1000);
    }
    this.currentWatchEpisodeId = null;
  }

  openInVlc(episodeId) {
    const url = `/api/episodes/${episodeId}/playlist.m3u`;
    window.location.href = url;
    this.showToast('Downloaded stream playlist (.m3u). Open it with VLC to play, or click "Watch" to view directly in your browser.', 'info');
  }

  openCurrentInVlc() {
    if (this.currentLiveChannelId) {
      this.openLiveInVlc(this.currentLiveChannelId);
    } else if (this.currentWatchEpisodeId) {
      this.openInVlc(this.currentWatchEpisodeId);
    }
  }

  // --- MP4 Export / Background Downloads ---
  async exportEpisode(episodeId) {
    try {
      const res = await this.api(`/api/episodes/${episodeId}/export`, { method: 'POST' });
      this.showToast('Background MP4 export started. Check "Downloads".', 'success');
      this.openExportsModal();
    } catch (err) {
      this.showToast(`Export failed: ${err.message}`, 'error');
    }
  }

  async openExportsModal() {
    document.getElementById('exportsModal').classList.add('active');
    await this.renderExportsList();
  }

  closeExportsModal() {
    document.getElementById('exportsModal').classList.remove('active');
  }

  async renderExportsList() {
    const listEl = document.getElementById('exportsList');
    try {
      const res = await this.api('/api/exports');
      const jobs = res.jobs || [];

      if (jobs.length === 0) {
        listEl.innerHTML = `<p style="color:var(--text-muted); font-size:0.9rem; text-align:center; padding:30px 0;">No MP4 exports recorded yet.</p>`;
        return;
      }

      listEl.innerHTML = jobs.map(j => {
        const isDone = j.status === 'completed';
        const isFailed = j.status === 'failed';
        const sizeMb = j.file_size ? `${(j.file_size / (1024 * 1024)).toFixed(1)} MB` : '';

        return `
          <div style="background:var(--bg-secondary); border:1px solid var(--border-subtle); border-radius:10px; padding:12px 16px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
              <span style="font-weight:600; font-size:0.9rem; color:#fff;">${this.escapeHtml(j.filename)}</span>
              <span style="font-size:0.75rem; text-transform:uppercase; font-weight:700; color:${isDone ? 'var(--accent-emerald)' : isFailed ? 'var(--accent-rose)' : 'var(--accent-cyan)'};">
                ${j.status}
              </span>
            </div>
            <div style="display:flex; align-items:center; justify-content:space-between; font-size:0.75rem; color:var(--text-dim); margin-bottom:8px;">
              <span>${j.title || ''} ${sizeMb ? `• ${sizeMb}` : ''}</span>
              <span>${j.progress ? Math.round(j.progress) + '%' : ''}</span>
            </div>
            <div class="progress-track" style="margin-bottom:8px;">
              <div class="progress-fill" style="width: ${j.progress || 0}%;"></div>
            </div>
            ${isDone ? `
              <div style="display:flex; justify-content:flex-end;">
                <a href="/downloads/${encodeURIComponent(j.filename)}" download class="btn btn-primary btn-sm">Download to PC</a>
              </div>
            ` : ''}
          </div>
        `;
      }).join('');
    } catch (err) {
      listEl.innerHTML = `<p style="color:var(--accent-rose);">Error loading exports: ${err.message}</p>`;
    }
  }

  // --- API Discovery & Debug Inspector ---
  async openDebugModal() {
    const modal = document.getElementById('debugModal');
    const content = document.getElementById('debugContent');
    modal.classList.add('active');
    content.textContent = 'Probing local Tablo hardware (port 8887 & 80) and Lighthouse cloud...';

    try {
      const data = await this.api('/api/debug/endpoints');
      content.textContent = JSON.stringify(data, null, 2);
    } catch (err) {
      content.textContent = `Inspector Error: ${err.message}`;
    }
  }

  closeDebugModal() {
    document.getElementById('debugModal').classList.remove('active');
  }

  // --- Sync / Refresh Library ---
  async refreshLibrary() {
    if (this.isSyncing) return;
    this.setSyncingState(true);
    try {
      await this.api('/api/library/refresh', { method: 'POST' });
      this.showToast('Tablo library sync initiated...', 'info');
    } catch (err) {
      this.showToast(`Sync failed: ${err.message}`, 'error');
      this.setSyncingState(false);
    }
  }

  setSyncingState(isSyncing) {
    this.isSyncing = isSyncing;
    const icon = document.getElementById('syncIcon');
    const text = document.getElementById('syncBtnText');
    if (isSyncing) {
      icon.style.animation = 'spin 1s linear infinite';
      text.textContent = 'Syncing...';
    } else {
      icon.style.animation = 'none';
      text.textContent = 'Refresh';
    }
  }

  async pollStatus() {
    try {
      const status = await this.api('/api/library/status');
      if (this.isSyncing && !status.is_syncing) {
        this.setSyncingState(false);
        this.showToast('Tablo library sync complete!', 'success');
        this.loadShows();
        this.fetchStorage();
      } else if (!this.isSyncing && status.is_syncing) {
        this.setSyncingState(true);
      }
    } catch (e) {
      // Ignore background poll errors
    }
  }

  // --- Formatting Helpers ---
  formatDate(dateStr) {
    if (!dateStr) return '';
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString('en-US', {
        weekday: 'short',
        month: 'short',
        day: 'numeric'
      });
    } catch (e) {
      return dateStr;
    }
  }

  escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // ==========================================================================
  // Scheduled Series Recording Management
  // ==========================================================================

  async loadScheduledSeries(forceToast = false) {
    try {
      const res = await this.api('/api/guide/scheduled');
      this.scheduledSeries = res.shows || [];
      
      const total = this.scheduledSeries.length;
      const newCount = this.scheduledSeries.filter(s => s.schedule_rule === 'new').length;
      const allEpsCount = this.scheduledSeries.filter(s => s.schedule_rule === 'all').length;

      const badge = document.getElementById('scheduledTabBadge');
      if (badge) badge.textContent = total;

      const filterAll = document.getElementById('scheduledFilterAllCount');
      if (filterAll) filterAll.textContent = total;

      const filterNew = document.getElementById('scheduledFilterNewCount');
      if (filterNew) filterNew.textContent = newCount;

      const filterAllEps = document.getElementById('scheduledFilterAllEpsCount');
      if (filterAllEps) filterAllEps.textContent = allEpsCount;

      this.renderScheduledGrid();
      if (forceToast) {
        this.showToast(`Found ${total} active series recordings on Tablo!`, 'success');
      }
    } catch (err) {
      console.error('Failed to load scheduled series:', err);
      const grid = document.getElementById('scheduledGrid');
      if (grid) {
        grid.innerHTML = `
          <div style="grid-column: 1 / -1; padding: 60px 0; text-align: center;">
            <p style="color:var(--accent-rose); font-weight:600;">Error loading scheduled recordings.</p>
            <button class="btn btn-ghost" style="margin-top:10px;" onclick="app.loadScheduledSeries(true)">Retry</button>
          </div>
        `;
      }
    }
  }

  setScheduledFilter(filter, btn) {
    this.scheduledFilter = filter;
    if (btn && btn.parentElement) {
      btn.parentElement.querySelectorAll('.pill-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
    }
    this.renderScheduledGrid();
  }

  onScheduledSearch(val) {
    this.scheduledSearchQuery = (val || '').toLowerCase().trim();
    this.renderScheduledGrid();
  }

  renderScheduledGrid() {
    const grid = document.getElementById('scheduledGrid');
    if (!grid) return;

    let items = this.scheduledSeries;

    if (this.scheduledFilter === 'new') {
      items = items.filter(s => s.schedule_rule === 'new');
    } else if (this.scheduledFilter === 'all_eps') {
      items = items.filter(s => s.schedule_rule === 'all');
    }

    if (this.scheduledSearchQuery) {
      items = items.filter(s => 
        (s.title || '').toLowerCase().includes(this.scheduledSearchQuery) ||
        (s.description || '').toLowerCase().includes(this.scheduledSearchQuery)
      );
    }

    if (!items || items.length === 0) {
      grid.innerHTML = `
        <div style="grid-column: 1 / -1; padding: 90px 0; text-align: center;">
          <h3 style="font-family:'Outfit'; font-size:1.3rem; font-weight:700; color:#fff; margin-bottom:8px;">
            ${this.scheduledSearchQuery ? 'No Matching Scheduled Shows' : 'No Scheduled Series'}
          </h3>
          <p style="color:var(--text-muted); font-size:0.9rem; margin-bottom:20px;">
            ${this.scheduledSearchQuery 
              ? `No scheduled shows match "${this.escapeHtml(this.scheduledSearchQuery)}"` 
              : 'You do not have any series recordings scheduled right now.'}
          </p>
          <button class="btn btn-primary" onclick="app.switchTab('guide')">
            Browse Guide to Schedule Shows
          </button>
        </div>
      `;
      return;
    }

    grid.innerHTML = items.map(show => {
      const isNew = show.schedule_rule === 'new';
      const badgeClass = isNew ? 'badge-rule-new' : 'badge-rule-all';
      const badgeText = isNew ? 'Record New' : 'Record All';
      const coverUrl = this.getImageUrl(show.cover_url || show.backdrop_url);
      const genres = Array.isArray(show.genres) ? show.genres.slice(0, 3).join(', ') : '';

      return `
        <div class="scheduled-card" id="scheduled-card-${this.escapeHtml(show.path)}">
          <div class="scheduled-card-media" onclick="app.openGuideDrawer('${this.escapeHtml(show.path)}')">
            <img src="${this.escapeHtml(coverUrl)}" alt="${this.escapeHtml(show.title)}" loading="lazy" onerror="this.onerror=null; this.src='/static/placeholder.svg';">
            <div class="guide-card-badge ${badgeClass}">
              <span class="unwatched-dot" style="background:#fff;"></span>
              <span>${badgeText}</span>
            </div>
          </div>
          <div class="scheduled-card-body">
            <h3 class="scheduled-card-title" onclick="app.openGuideDrawer('${this.escapeHtml(show.path)}')">
              ${this.escapeHtml(show.title)}
            </h3>
            <div class="guide-card-meta">
              ${genres ? `<span>${this.escapeHtml(genres)}</span>` : ''}
              <span>•</span>
              <span style="color:var(--accent-cyan); font-weight:600;">${show.airing_count || 0} airings in guide</span>
            </div>
            <p class="guide-card-desc">${this.escapeHtml(show.description || 'No description available.')}</p>

            <div class="scheduled-card-actions">
              ${isNew ? `
                <button class="action-btn-pill action-btn-all" onclick="app.quickSetSeriesRule('${this.escapeHtml(show.path)}', 'all', '${this.escapeHtml(show.title)}', event)" title="Switch to record all episodes including reruns">
                  Record All
                </button>
              ` : `
                <button class="action-btn-pill action-btn-new" onclick="app.quickSetSeriesRule('${this.escapeHtml(show.path)}', 'new', '${this.escapeHtml(show.title)}', event)" title="Switch to record new episodes only">
                  Record New
                </button>
              `}
              <button class="action-btn-pill action-btn-stop" onclick="app.quickSetSeriesRule('${this.escapeHtml(show.path)}', 'none', '${this.escapeHtml(show.title)}', event)" title="Cancel/Stop series recording">
                Stop
              </button>
              <button class="btn btn-ghost btn-sm" onclick="app.openGuideDrawer('${this.escapeHtml(show.path)}')" style="font-size:0.75rem;" title="View upcoming broadcast airings">
                Airings
              </button>
            </div>
          </div>
        </div>
      `;
    }).join('');
  }

  // ==========================================================================
  // Guide Search & Discovery
  // ==========================================================================

  async loadGuideShows(force = false) {
    const grid = document.getElementById('guideGrid');
    try {
      const params = new URLSearchParams();
      if (this.guideHighlight) {
        params.append('highlight', this.guideHighlight);
      }
      if (this.guideCategory && this.guideCategory !== 'all') {
        params.append('category', this.guideCategory);
      }
      if (this.guideRule) {
        params.append('rule', this.guideRule);
      }
      if (this.guideSearchQuery.trim()) {
        params.append('search', this.guideSearchQuery.trim());
      }
      params.append('sort', this.guideSort);
      params.append('limit', '200');

      const res = await this.api(`/api/guide/shows?${params.toString()}`);
      this.guideShows = res.shows || [];

      const badge = document.getElementById('guideTabBadge');
      if (badge && res.count !== undefined) {
        badge.textContent = res.count;
      }

      // Update highlight pill badges
      if (res.highlights) {
        const pBadge = document.getElementById('guideBadgePrimetime');
        if (pBadge && res.highlights.primetime_new !== undefined) {
          pBadge.textContent = res.highlights.primetime_new;
        }
        const sBadge = document.getElementById('guideBadgePremieres');
        if (sBadge && res.highlights.premieres !== undefined) {
          sBadge.textContent = res.highlights.premieres;
        }
      }

      this.renderGuideGrid();
    } catch (err) {
      console.error('Error loading guide shows:', err);
      if (grid) {
        grid.innerHTML = `
          <div style="grid-column: 1 / -1; padding: 60px 0; text-align: center;">
            <p style="color:var(--accent-rose); font-weight:600;">Failed to load guide shows.</p>
            <button class="btn btn-ghost" style="margin-top:10px;" onclick="app.loadGuideShows()">Retry</button>
          </div>
        `;
      }
    }
  }

  onGuideSearchInput(val) {
    this.guideSearchQuery = val || '';
    clearTimeout(this.guideSearchTimeout);
    this.guideSearchTimeout = setTimeout(() => {
      this.loadGuideShows();
    }, 220);
  }

  setGuideHighlight(highlight, btn) {
    if (this.guideHighlight === highlight) {
      // Toggle off when clicked again
      this.guideHighlight = null;
      if (btn && btn.parentElement) {
        btn.parentElement.querySelectorAll('.pill-btn').forEach(b => b.classList.remove('active'));
        const firstBtn = btn.parentElement.querySelector('.pill-btn');
        if (firstBtn) firstBtn.classList.add('active');
      }
    } else {
      this.guideHighlight = highlight;
      this.guideCategory = 'all';
      this.guideRule = '';
      if (btn && btn.parentElement) {
        btn.parentElement.querySelectorAll('.pill-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
      }
    }
    this.loadGuideShows();
  }

  setGuideCategory(cat, btn) {
    this.guideCategory = cat;
    this.guideHighlight = null;
    if (btn && btn.parentElement) {
      btn.parentElement.querySelectorAll('.pill-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
    }
    this.loadGuideShows();
  }

  setGuideRule(rule, btn) {
    this.guideRule = rule;
    this.guideHighlight = null;
    if (btn && btn.parentElement) {
      btn.parentElement.querySelectorAll('.pill-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
    }
    this.loadGuideShows();
  }

  onGuideSortChange(val) {
    this.guideSort = val;
    this.loadGuideShows();
  }

  formatNextAiring(isoStr) {
    if (!isoStr) return '';
    try {
      const d = new Date(isoStr);
      const now = new Date();
      const isToday = d.toDateString() === now.toDateString();
      const tmrw = new Date(now);
      tmrw.setDate(tmrw.getDate() + 1);
      const isTomorrow = d.toDateString() === tmrw.toDateString();

      const timePart = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
      if (isToday) return `Tonight ${timePart}`;
      if (isTomorrow) return `Tomorrow ${timePart}`;
      const dayPart = d.toLocaleDateString('en-US', { weekday: 'short', month: 'numeric', day: 'numeric' });
      return `${dayPart} ${timePart}`;
    } catch (e) {
      return '';
    }
  }

  renderGuideGrid() {
    const grid = document.getElementById('guideGrid');
    if (!grid) return;

    if (!this.guideShows || this.guideShows.length === 0) {
      const filterLabel = this.guideHighlight === 'primetime_new'
        ? 'No Primetime shows with new episodes found.'
        : (this.guideHighlight === 'premieres' ? 'No Season Premieres currently detected.' : 'No shows found in the OTA TV guide.');

      grid.innerHTML = `
        <div style="grid-column: 1 / -1; padding: 90px 0; text-align: center;">
          <h3 style="font-family:'Outfit'; font-size:1.3rem; font-weight:700; color:#fff; margin-bottom:8px;">No Shows Found</h3>
          <p style="color:var(--text-muted); font-size:0.9rem;">
            ${this.guideSearchQuery ? `No broadcast shows match "${this.escapeHtml(this.guideSearchQuery)}"` : filterLabel}
          </p>
        </div>
      `;
      return;
    }

    grid.innerHTML = this.guideShows.map(show => {
      const rule = show.schedule_rule || 'none';
      const isNew = rule === 'new';
      const isAll = rule === 'all';
      const isScheduled = isNew || isAll;

      let badgeClass = 'badge-rule-none';
      let badgeText = 'Not Scheduled';
      if (isNew) {
        badgeClass = 'badge-rule-new';
        badgeText = 'Record New';
      } else if (isAll) {
        badgeClass = 'badge-rule-all';
        badgeText = 'Record All';
      }

      // Highlight badges (Season Premiere / Primetime New)
      let highlightBadgeHtml = '';
      if (show.has_premiere) {
        highlightBadgeHtml = `<div class="guide-highlight-badge badge-highlight-premiere"><span>🌟 Premiere</span></div>`;
      } else if (show.has_primetime_new) {
        highlightBadgeHtml = `<div class="guide-highlight-badge badge-highlight-primetime"><span>⭐ Primetime</span></div>`;
      }

      // Next broadcast pill
      let nextAiringHtml = '';
      if (show.next_airing && show.next_airing.datetime) {
        const nextTime = this.formatNextAiring(show.next_airing.datetime);
        const net = show.next_airing.network || show.next_airing.call_sign || '';
        let epInfo = '';
        if (show.next_airing.season_number && show.next_airing.episode_number) {
          epInfo = ` S${show.next_airing.season_number}E${show.next_airing.episode_number}`;
        }
        if (nextTime) {
          nextAiringHtml = `<span class="guide-next-pill" title="Next: ${this.escapeHtml(show.next_airing.title || '')}">🕒 ${this.escapeHtml(nextTime)}${epInfo}${net ? ` • ${this.escapeHtml(net)}` : ''}</span>`;
        }
      }

      const coverUrl = this.getImageUrl(show.cover_url || show.backdrop_url);
      const genres = Array.isArray(show.genres) ? show.genres.slice(0, 3).join(', ') : '';

      return `
        <div class="guide-card" id="guide-card-${this.escapeHtml(show.path)}">
          <div class="guide-card-media" onclick="app.openGuideDrawer('${this.escapeHtml(show.path)}')">
            <img src="${this.escapeHtml(coverUrl)}" alt="${this.escapeHtml(show.title)}" loading="lazy" onerror="this.onerror=null; this.src='/static/placeholder.svg';">
            ${highlightBadgeHtml}
            <div class="guide-card-badge ${badgeClass}">
              <span>${badgeText}</span>
            </div>
          </div>
          <div class="guide-card-body">
            <h3 class="guide-card-title" onclick="app.openGuideDrawer('${this.escapeHtml(show.path)}')">
              ${this.escapeHtml(show.title)}
            </h3>
            <div class="guide-card-meta">
              ${genres ? `<span>${this.escapeHtml(genres)}</span><span>•</span>` : ''}
              <span style="color:var(--accent-cyan); font-weight:600;">${show.airing_count || 0} airings</span>
              ${nextAiringHtml}
            </div>
            <p class="guide-card-desc">${this.escapeHtml(show.description || 'No description available.')}</p>

            <div class="guide-card-actions">
              ${!isScheduled ? `
                <button class="action-btn-pill action-btn-new" onclick="app.quickSetSeriesRule('${this.escapeHtml(show.path)}', 'new', '${this.escapeHtml(show.title)}', event)" title="Record new episodes">
                  + Record New
                </button>
                <button class="action-btn-pill action-btn-all" onclick="app.quickSetSeriesRule('${this.escapeHtml(show.path)}', 'all', '${this.escapeHtml(show.title)}', event)" title="Record all episodes">
                  + Record All
                </button>
              ` : `
                ${isNew ? `
                  <button class="action-btn-pill action-btn-all" onclick="app.quickSetSeriesRule('${this.escapeHtml(show.path)}', 'all', '${this.escapeHtml(show.title)}', event)" title="Switch to record all episodes">
                    Record All
                  </button>
                ` : `
                  <button class="action-btn-pill action-btn-new" onclick="app.quickSetSeriesRule('${this.escapeHtml(show.path)}', 'new', '${this.escapeHtml(show.title)}', event)" title="Switch to record new episodes">
                    Record New
                  </button>
                `}
                <button class="action-btn-pill action-btn-stop" onclick="app.quickSetSeriesRule('${this.escapeHtml(show.path)}', 'none', '${this.escapeHtml(show.title)}', event)" title="Stop series recording">
                  Stop
                </button>
              `}
              <button class="btn btn-ghost btn-sm" onclick="app.openGuideDrawer('${this.escapeHtml(show.path)}')" style="font-size:0.75rem;">
                Airings
              </button>
            </div>
          </div>
        </div>
      `;
    }).join('');
  }

  // ==========================================================================
  // Quick Rule Setting & Guide Drawer Logic
  // ==========================================================================

  async quickSetSeriesRule(path, rule, title, event) {
    if (event) {
      event.stopPropagation();
      event.preventDefault();
    }

    try {
      const res = await this.api('/api/guide/series/schedule', {
        method: 'POST',
        body: JSON.stringify({ path, rule })
      });

      // Update in memory guide shows
      const gShow = this.guideShows.find(s => s.path === path);
      if (gShow) gShow.schedule_rule = rule;

      // Update in memory scheduled series
      if (rule === 'none') {
        this.scheduledSeries = this.scheduledSeries.filter(s => s.path !== path);
      } else {
        const sIndex = this.scheduledSeries.findIndex(s => s.path === path);
        if (sIndex >= 0) {
          this.scheduledSeries[sIndex].schedule_rule = rule;
        } else if (gShow) {
          this.scheduledSeries.push({ ...gShow, schedule_rule: rule });
        }
      }

      // Update badges
      const schedBadge = document.getElementById('scheduledTabBadge');
      if (schedBadge) schedBadge.textContent = this.scheduledSeries.length;

      // Re-render
      this.renderGuideGrid();
      this.renderScheduledGrid();

      const label = rule === 'new' ? 'Record New Episodes' : (rule === 'all' ? 'Record All Episodes' : 'Recording Stopped');
      this.showToast(`${title}: ${label}!`, rule === 'none' ? 'info' : 'success');
    } catch (err) {
      this.showToast(`Failed to update schedule: ${err.message}`, 'error');
    }
  }

  async openGuideDrawer(path) {
    // Look up in guide shows or scheduled series
    let show = this.guideShows.find(s => s.path === path) || this.scheduledSeries.find(s => s.path === path);
    if (!show) {
      try {
        show = await this.api(`/api/guide/series?path=${encodeURIComponent(path)}`);
      } catch (err) {
        this.showToast(`Error opening show: ${err.message}`, 'error');
        return;
      }
    }

    this.currentGuideSeries = show;

    // Populate drawer header
    document.getElementById('guideDrawerShowTitle').textContent = show.title;
    document.getElementById('guideDrawerShowDesc').textContent = show.description || 'No description provided.';
    document.getElementById('guideDrawerCategory').textContent = (show.category || 'Series').toUpperCase();
    document.getElementById('guideDrawerAiringsCount').textContent = `${show.airing_count || 0} Airings in Guide`;
    document.getElementById('guideDrawerAirDate').textContent = show.orig_air_date ? `Premiered ${show.orig_air_date}` : '';

    const posterImg = document.getElementById('guideDrawerPosterImg');
    const coverUrl = this.getImageUrl(show.cover_url || show.backdrop_url);
    posterImg.onerror = () => { posterImg.src = '/static/placeholder.svg'; };
    posterImg.src = coverUrl;

    // Update rule card
    this.updateGuideDrawerRuleUI(show.schedule_rule || 'none');

    // Open drawer
    document.getElementById('guideDrawerBackdrop').classList.add('active');
    document.getElementById('guideDrawerPanel').classList.add('active');

    // Fetch upcoming broadcast episodes
    this.loadGuideUpcomingAirings(path);
  }

  closeGuideDrawer() {
    document.getElementById('guideDrawerBackdrop').classList.remove('active');
    document.getElementById('guideDrawerPanel').classList.remove('active');
    this.currentGuideSeries = null;
  }

  updateGuideDrawerRuleUI(rule) {
    const pill = document.getElementById('guideDrawerStatusPill');
    const btnNew = document.getElementById('btnRuleNew');
    const btnAll = document.getElementById('btnRuleAll');
    const btnNone = document.getElementById('btnRuleNone');

    [btnNew, btnAll, btnNone].forEach(b => {
      if (b) b.classList.remove('active');
    });

    if (pill) {
      pill.className = `rule-status-pill ${rule}`;
      if (rule === 'new') {
        pill.textContent = '🟢 Recording New';
        if (btnNew) btnNew.classList.add('active');
      } else if (rule === 'all') {
        pill.textContent = '🔵 Recording All';
        if (btnAll) btnAll.classList.add('active');
      } else {
        pill.textContent = '⚪ Not Scheduled';
        if (btnNone) btnNone.classList.add('active');
      }
    }
  }

  async setSeriesScheduleRule(rule) {
    if (!this.currentGuideSeries) return;
    const path = this.currentGuideSeries.path;
    const title = this.currentGuideSeries.title;

    try {
      await this.api('/api/guide/series/schedule', {
        method: 'POST',
        body: JSON.stringify({ path, rule })
      });

      this.currentGuideSeries.schedule_rule = rule;
      this.updateGuideDrawerRuleUI(rule);

      // Also update in lists
      const g = this.guideShows.find(s => s.path === path);
      if (g) g.schedule_rule = rule;

      if (rule === 'none') {
        this.scheduledSeries = this.scheduledSeries.filter(s => s.path !== path);
      } else {
        const sIdx = this.scheduledSeries.findIndex(s => s.path === path);
        if (sIdx >= 0) {
          this.scheduledSeries[sIdx].schedule_rule = rule;
        } else {
          this.scheduledSeries.push({ ...this.currentGuideSeries, schedule_rule: rule });
        }
      }

      const schedBadge = document.getElementById('scheduledTabBadge');
      if (schedBadge) schedBadge.textContent = this.scheduledSeries.length;

      this.renderGuideGrid();
      this.renderScheduledGrid();

      // Refresh airings to reflect updated schedule states
      this.loadGuideUpcomingAirings(path);

      const label = rule === 'new' ? 'Recording New Episodes' : (rule === 'all' ? 'Recording All Episodes' : 'Recording Canceled');
      this.showToast(`${title}: ${label}!`, rule === 'none' ? 'info' : 'success');
    } catch (err) {
      this.showToast(`Failed to update schedule: ${err.message}`, 'error');
    }
  }

  async loadGuideUpcomingAirings(seriesPath) {
    const list = document.getElementById('guideAiringsList');
    const countBadge = document.getElementById('guideAiringsCountBadge');
    if (!list) return;

    list.innerHTML = `
      <div style="padding: 40px 0; text-align: center;">
        <div class="spinner" style="margin-bottom:12px;"></div>
        <p style="color:var(--text-muted); font-size:0.85rem;">Scanning upcoming broadcasts on local channels...</p>
      </div>
    `;

    try {
      const res = await this.api(`/api/guide/series/episodes?series_path=${encodeURIComponent(seriesPath)}`);
      const episodes = res.episodes || [];
      if (countBadge) countBadge.textContent = `${episodes.length} Upcoming`;

      if (episodes.length === 0) {
        list.innerHTML = `
          <div style="padding: 30px 0; text-align: center;">
            <p style="color:var(--text-muted); font-size:0.85rem;">No upcoming airings scheduled on your channels in the next 14 days.</p>
          </div>
        `;
        return;
      }

      list.innerHTML = episodes.map(ep => {
        const channel = ep.channel || {};
        const chDisplay = `${channel.call_sign || channel.name || ''} ${channel.major ? `${channel.major}.${channel.minor}` : ''} ${channel.network ? `• ${channel.network}` : ''}`.trim();
        const airTimeFormatted = this.formatAiringDateTime(ep.air_datetime, ep.duration);
        const epNumVal = ep.episode_number || ep.number || 0;
        let epTitle = ep.title ? ep.title.trim() : '';
        if (!epTitle || epTitle === 'Episode') {
          epTitle = epNumVal > 0 ? `Episode ${epNumVal}` : 'Untitled Episode';
        }
        const sNum = ep.season_number > 0 ? `S${String(ep.season_number).padStart(2, '0')}` : '';
        const eNum = epNumVal > 0 ? `E${String(epNumVal).padStart(2, '0')}` : '';
        const seasonEp = (sNum || eNum) ? `${sNum}${eNum} • ` : '';
        const isScheduled = !!ep.is_scheduled;
        const isNew = (ep.qualifiers || []).includes('new');

        return `
          <div class="guide-airing-card" id="airing-card-${this.escapeHtml(ep.path)}">
            <div class="airing-top-row">
              <div class="airing-channel-badge">
                ${channel.logo_url ? `<img src="${this.escapeHtml(channel.logo_url)}" class="airing-channel-logo" alt="${this.escapeHtml(channel.network || '')}">` : ''}
                <span class="airing-channel-text">${this.escapeHtml(chDisplay || 'Local Channel')}</span>
              </div>
              <span class="airing-time-text">${airTimeFormatted}</span>
            </div>

            <div class="airing-episode-title">
              <span style="color:var(--accent-cyan);">${seasonEp}</span>${this.escapeHtml(epTitle)}
            </div>

            ${ep.description ? `<p class="airing-episode-desc">${this.escapeHtml(ep.description)}</p>` : ''}

            <div class="airing-bottom-row">
              <div class="airing-tags">
                ${isNew ? '<span class="airing-tag new">NEW</span>' : ''}
                <span class="airing-tag hd">HD</span>
              </div>

              <button class="airing-schedule-toggle ${isScheduled ? 'scheduled' : 'unscheduled'}" 
                onclick="app.toggleEpisodeSchedule('${this.escapeHtml(ep.path)}', ${!isScheduled}, this)">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  ${isScheduled ? '<polyline points="20 6 9 17 4 12"/>' : '<line x1="12" x2="12" y1="5" y2="19"/><line x1="5" x2="19" y1="12" y2="12"/>'}
                </svg>
                <span>${isScheduled ? 'Scheduled' : 'Record Episode'}</span>
              </button>
            </div>
          </div>
        `;
      }).join('');
    } catch (err) {
      list.innerHTML = `
        <div style="padding: 24px 0; text-align: center;">
          <p style="color:var(--accent-rose); font-size:0.85rem;">Failed to fetch airings: ${this.escapeHtml(err.message)}</p>
        </div>
      `;
    }
  }

  async toggleEpisodeSchedule(path, newScheduledState, btn) {
    if (btn) {
      btn.disabled = true;
      btn.style.opacity = '0.6';
    }

    try {
      await this.api('/api/guide/episodes/schedule', {
        method: 'POST',
        body: JSON.stringify({ path, scheduled: newScheduledState })
      });

      this.showToast(
        newScheduledState ? 'Episode scheduled to record!' : 'Episode recording cancelled!',
        newScheduledState ? 'success' : 'info'
      );

      // Re-fetch airings in drawer
      if (this.currentGuideSeries) {
        this.loadGuideUpcomingAirings(this.currentGuideSeries.path);
      }
    } catch (err) {
      this.showToast(`Error: ${err.message}`, 'error');
      if (btn) {
        btn.disabled = false;
        btn.style.opacity = '1';
      }
    }
  }

  async syncGuide(force = false) {
    try {
      await this.api('/api/guide/sync', { method: 'POST' });
      this.showToast('OTA broadcast guide sync initiated in background...', 'info');
      setTimeout(() => {
        this.loadGuideShows();
        this.loadScheduledSeries();
      }, 5000);
    } catch (err) {
      this.showToast(`Guide sync failed: ${err.message}`, 'error');
    }
  }

  formatAiringDateTime(isoStr, durationSec) {
    if (!isoStr) return '--';
    try {
      const d = new Date(isoStr);
      const datePart = d.toLocaleDateString('en-US', {
        weekday: 'short',
        month: 'short',
        day: 'numeric'
      });
      const timePart = d.toLocaleTimeString('en-US', {
        hour: 'numeric',
        minute: '2-digit'
      });
      const durMins = Math.round((durationSec || 0) / 60);
      const durStr = durMins >= 60 ? `${Math.floor(durMins / 60)}h ${durMins % 60}m` : `${durMins}m`;
      return `${datePart} • ${timePart} (${durStr})`;
    } catch (e) {
      return isoStr;
    }
  }

  // ==================== LIVE TV CONTROLLER ====================

  async checkTuners() {
    try {
      const res = await this.api('/api/live/tuners');
      const badge = document.getElementById('tunerStatusBadge');
      const text = document.getElementById('tunerStatusText');
      if (!badge || !text) return;

      const total = res.total || 2;
      const inUse = res.in_use || 0;
      const avail = res.available ?? (total - inUse);

      if (inUse > 0) {
        badge.classList.add('active-tuner');
        text.textContent = `Tuners: ${inUse}/${total} In Use`;
        badge.style.borderColor = 'rgba(239, 68, 68, 0.4)';
        badge.style.background = 'rgba(239, 68, 68, 0.12)';
      } else {
        badge.classList.remove('active-tuner');
        text.textContent = `Tuners: ${avail}/${total} Free`;
        badge.style.borderColor = 'rgba(16, 185, 129, 0.3)';
        badge.style.background = 'rgba(16, 185, 129, 0.08)';
      }
    } catch (e) {
      console.warn('Failed to fetch tuner status:', e);
    }
  }

  startLiveClock() {
    const update = () => {
      const now = new Date();
      const clockEl = document.getElementById('epgClockText');
      if (clockEl) {
        clockEl.textContent = now.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
      }

      const dateBadge = document.getElementById('epgDateBadge');
      if (dateBadge) {
        const targetDate = new Date(Date.now() + (this.epgStartOffset || 0) * 3600000);
        const isToday = targetDate.toDateString() === now.toDateString();
        const dateStr = targetDate.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
        dateBadge.textContent = isToday ? `Today • ${dateStr}` : dateStr;
      }

      // Update vertical red line in EPG grid if rendered
      if (this.epgData && this.epgData.window_start) {
        const windowStartMs = new Date(this.epgData.window_start).getTime();
        const windowEndMs = new Date(this.epgData.window_end).getTime();
        const nowMs = Date.now();
        const lineEl = document.getElementById('epgNowLine');

        if (windowStartMs <= nowMs && nowMs <= windowEndMs) {
          const nowOffsetMins = (nowMs - windowStartMs) / 60000;
          const leftPx = 250 + Math.round(nowOffsetMins * 8);
          if (lineEl) {
            lineEl.style.display = 'block';
            lineEl.style.left = `${leftPx}px`;
          }
        } else if (lineEl) {
          lineEl.style.display = 'none';
        }
      }
    };

    update();
    if (this.epgClockInterval) clearInterval(this.epgClockInterval);
    this.epgClockInterval = setInterval(update, 1000);
  }

  setEpgCategory(cat, btn) {
    this.epgCategory = cat;
    const items = document.querySelectorAll('.epg-nav-item');
    items.forEach(i => i.classList.remove('active'));
    if (btn) btn.classList.add('active');

    const catTitles = {
      'ota': 'Local Networks (OTA)',
      'all': 'All Channels',
      'fast': 'Streaming (FAST)',
      'news': 'News & Information',
      'sports': 'Sports',
      'entertainment': 'Entertainment & Movies'
    };
    const titleEl = document.getElementById('epgActiveCatName');
    if (titleEl) titleEl.textContent = catTitles[cat] || 'Guide';

    this.renderEpgGrid();
  }

  shiftEpgTime(deltaHours) {
    this.epgStartOffset += deltaHours;
    this.loadLiveEpg(false, true);
  }

  jumpEpgToNow() {
    this.epgStartOffset = 0;
    this.loadLiveEpg(false, true);
  }

  async loadLiveEpg(forceToast = false, scrollToNow = false) {
    try {
      let startIso = null;
      if (this.epgStartOffset !== 0) {
        const d = new Date();
        d.setHours(d.getHours() + this.epgStartOffset);
        startIso = d.toISOString();
      }

      const url = `/api/live/epg?hours=${this.epgHours}${startIso ? '&start_iso=' + encodeURIComponent(startIso) : ''}`;
      const res = await this.api(url);
      this.epgData = res;

      const badge = document.getElementById('liveTabBadge');
      if (badge) badge.textContent = res.count;

      const otaCount = res.channels.filter(c => c.kind === 'ota').length;
      const fastCount = res.channels.filter(c => c.kind !== 'ota').length;

      const countOtaEl = document.getElementById('countCatOta');
      if (countOtaEl) countOtaEl.textContent = otaCount;
      const countFastEl = document.getElementById('countCatFast');
      if (countFastEl) countFastEl.textContent = fastCount;
      const countAllEl = document.getElementById('countCatAll');
      if (countAllEl) countAllEl.textContent = res.count;

      this.renderEpgGrid(scrollToNow);

      if (forceToast) {
        this.showToast(`TV Guide updated (${res.count} channels)`, 'success');
      }
    } catch (err) {
      console.error('Failed to load live EPG:', err);
      this.showToast(`Error loading TV Guide: ${err.message}`, 'error');
    }
  }

  onLiveSearchInput(query) {
    clearTimeout(this.liveSearchTimeout);
    this.liveSearchTimeout = setTimeout(() => {
      this.liveSearchQuery = (query || '').toLowerCase().trim();
      this.renderEpgGrid();
    }, 200);
  }

  renderEpgGrid(shouldScrollToNow = false) {
    const board = document.getElementById('epgGridBoard');
    if (!board || !this.epgData || !this.epgData.slots) return;

    const { window_start, window_end, slots, channels } = this.epgData;
    const windowStartMs = new Date(window_start).getTime();
    const windowEndMs = new Date(window_end).getTime();
    const totalSlotWidth = slots.length * 240;

    // Filter channels
    let filtered = channels.filter(c => {
      if (this.epgCategory === 'ota' && c.kind !== 'ota') return false;
      if (this.epgCategory === 'fast' && c.kind !== 'fast') return false;

      const combinedText = `${c.name} ${c.call_sign} ${c.network}`.toLowerCase();
      if (this.epgCategory === 'news' && !combinedText.match(/news|bloomberg|scripps|cheddar|weather|wrtv|wthr|wttv|wxin/)) return false;
      if (this.epgCategory === 'sports' && !combinedText.match(/sport|outside|stadium|surf|fight|racing|motor/)) return false;
      if (this.epgCategory === 'entertainment' && !combinedText.match(/ion|movie|comedy|drama|classic|hallmark|film|bachelor|portlandia|wfyi/)) return false;

      if (this.liveSearchQuery) {
        const q = this.liveSearchQuery;
        const nameMatch = combinedText.includes(q);
        const airingsMatch = c.airings && c.airings.some(a => (a.title || '').toLowerCase().includes(q) || (a.episode_title || '').toLowerCase().includes(q));
        if (!nameMatch && !airingsMatch) return false;
      }
      return true;
    });

    if (filtered.length === 0) {
      board.innerHTML = `
        <div style="padding: 80px 20px; text-align: center; color: var(--text-muted); width: 100%;">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin: 0 auto 16px; opacity: 0.4;">
            <polygon points="5 3 19 12 5 21 5 3"/>
          </svg>
          <h3 style="font-size: 1.15rem; color: #fff; margin-bottom: 6px;">No Channels Match Filter</h3>
          <p style="font-size: 0.85rem;">Select "All Channels" or "Local Networks" on the left menu.</p>
        </div>
      `;
      return;
    }

    // Reset item map for modal click handlers
    this.epgItemsMap = {};

    // 1. Render Header Row (Sticky top)
    const headerSlotsHtml = slots.map(s => {
      const d = new Date(s.iso);
      const slotTimeStr = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
      return `<div class="epg-time-slot-cell">${slotTimeStr}</div>`;
    }).join('');

    const headerRowHtml = `
      <div class="epg-header-row">
        <div class="epg-header-channel-cell">CHANNELS</div>
        <div style="display:flex; width:${totalSlotWidth}px;">
          ${headerSlotsHtml}
        </div>
      </div>
    `;

    // 2. Render Channel Schedule Rows
    const nowMs = Date.now();
    let channelRowsHtml = '';

    filtered.forEach((c, chIdx) => {
      const logoHtml = c.logo_url
        ? `<img src="${this.escapeHtml(c.logo_url)}" alt="${this.escapeHtml(c.call_sign)}" class="epg-ch-logo">`
        : `<div class="epg-ch-logo-fallback">${this.escapeHtml(c.call_sign || c.network || 'TV')}</div>`;

      // Schedule blocks inside row track
      const airings = c.airings || [];
      const blocksHtml = airings.map((a, aIdx) => {
        const key = `epg_${c.channel_id}_${chIdx}_${aIdx}`;
        this.epgItemsMap[key] = { airing: a, channel: c };

        const airStartMs = new Date(a.air_datetime).getTime();
        const airEndMs = airStartMs + (a.duration * 1000);

        const clampedStart = Math.max(windowStartMs, airStartMs);
        const clampedEnd = Math.min(windowEndMs, airEndMs);

        if (clampedEnd <= clampedStart) return '';

        const offsetMins = (clampedStart - windowStartMs) / 60000;
        const durationMins = (clampedEnd - clampedStart) / 60000;

        const leftPx = Math.round(offsetMins * 8);
        const widthPx = Math.max(50, Math.round(durationMins * 8 - 3));

        const isOnAir = (airStartMs <= nowMs && nowMs < airEndMs);
        const durMins = Math.round(a.duration / 60);
        const durStr = durMins >= 60 ? `${Math.floor(durMins / 60)} hr${durMins % 60 > 0 ? ' ' + (durMins % 60) + 'm' : ''}` : `${durMins} mins`;
        const metaStr = `${durStr}${a.season_number ? ' • S' + a.season_number : ''}${a.episode_number ? ' E' + a.episode_number : ''}`;

        return `
          <div class="epg-program-cell ${isOnAir ? 'on-air' : ''}" 
               style="left: ${leftPx}px; width: ${widthPx}px;"
               data-left="${leftPx}"
               data-width="${widthPx}"
               onclick="app.openEpgModal('${key}')"
               title="${this.escapeHtml(a.title)} (${durStr})">
            <div class="epg-cell-inner">
              <div class="epg-prog-title">${this.escapeHtml(a.title)}</div>
              <div class="epg-prog-sub">
                ${isOnAir ? '<span class="epg-badge-onair"><span class="epg-onair-dot"></span>ON AIR</span>' : ''}
                <span>${this.escapeHtml(metaStr)}</span>
                ${a.is_new ? '<span class="epg-badge-new">NEW</span>' : ''}
                ${a.is_premiere ? '<span class="epg-badge-prem">PREMIERE</span>' : ''}
              </div>
            </div>
          </div>
        `;
      }).join('');

      // Format Channel Number and Clean Title
      const numStr = (c.major && c.major > 0) ? `${c.major}.${c.minor}` : '';
      let chTitle = c.name || c.call_sign || '';
      if (numStr && chTitle.startsWith(numStr)) {
        chTitle = chTitle.replace(numStr, '').trim();
      }

      // Subtitle: Network or Call sign + Resolution
      let chSub = '';
      const net = (c.network || '').trim();
      if (net && net.toLowerCase() !== chTitle.toLowerCase() && net.toLowerCase() !== (c.call_sign || '').toLowerCase()) {
        chSub = net;
      } else if (c.call_sign && c.call_sign.toLowerCase() !== chTitle.toLowerCase()) {
        chSub = c.call_sign;
      }
      if (c.resolution) {
        chSub = chSub ? `${chSub} • ${c.resolution}` : c.resolution;
      }

      channelRowsHtml += `
        <div class="epg-channel-row">
          <div class="epg-channel-col" onclick="app.watchLiveChannel('${this.escapeHtml(c.channel_id)}', '${this.escapeHtml(chTitle)}', '${this.escapeHtml(chTitle)}')" title="Watch ${this.escapeHtml(chTitle)} Live">
            <div class="epg-ch-left">
              ${logoHtml}
              <div class="epg-ch-info">
                <div class="epg-ch-number">
                  ${numStr ? `<span class="epg-ch-major-minor">${this.escapeHtml(numStr)}</span> ` : ''}${this.escapeHtml(chTitle)}
                </div>
                ${chSub ? `<div class="epg-ch-name">${this.escapeHtml(chSub)}</div>` : ''}
              </div>
            </div>
            <button class="epg-ch-play-btn" title="Watch Live Stream">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            </button>
          </div>

          <div class="epg-schedule-track" style="width: ${totalSlotWidth}px;">
            ${blocksHtml}
          </div>
        </div>
      `;
    });

    // 3. Current Time Vertical Line Marker
    let nowLineHtml = '';
    let nowLeftPx = 250;
    if (windowStartMs <= nowMs && nowMs <= windowEndMs) {
      const nowOffsetMins = (nowMs - windowStartMs) / 60000;
      nowLeftPx = 250 + Math.round(nowOffsetMins * 8);
      nowLineHtml = `<div class="epg-now-line" id="epgNowLine" style="left: ${nowLeftPx}px;"><div class="epg-now-dot"></div></div>`;
    }

    board.innerHTML = `
      ${headerRowHtml}
      ${channelRowsHtml}
      ${nowLineHtml}
    `;

    // 4. Auto-scroll to current time position & pin sticky titles
    const scrollEl = document.getElementById('epgScrollWrapper');
    this.setupEpgScrollSticky();

    if (scrollEl && (shouldScrollToNow || !this.hasScrolledToNow)) {
      setTimeout(() => {
        scrollEl.scrollLeft = Math.max(0, nowLeftPx - 350);
        this.hasScrolledToNow = true;
        this.updateEpgStickyTitles();
      }, 50);
    } else {
      this.updateEpgStickyTitles();
    }
  }

  setupEpgScrollSticky() {
    const scrollEl = document.getElementById('epgScrollWrapper');
    if (!scrollEl || this._epgScrollBound) return;
    this._epgScrollBound = true;

    let ticking = false;
    scrollEl.addEventListener('scroll', () => {
      if (!ticking) {
        requestAnimationFrame(() => {
          this.updateEpgStickyTitles();
          ticking = false;
        });
        ticking = true;
      }
    }, { passive: true });
  }

  updateEpgStickyTitles() {
    const scrollEl = document.getElementById('epgScrollWrapper');
    if (!scrollEl) return;
    const scrollLeft = scrollEl.scrollLeft;

    const cells = scrollEl.querySelectorAll('.epg-program-cell');
    for (let i = 0; i < cells.length; i++) {
      const cell = cells[i];
      const left = parseFloat(cell.dataset.left || 0);
      const width = parseFloat(cell.dataset.width || 0);
      const inner = cell.firstElementChild;
      if (!inner) continue;

      if (scrollLeft > left && scrollLeft < left + width - 40) {
        const shift = Math.min(scrollLeft - left, width - 60);
        inner.style.transform = `translateX(${shift}px)`;
      } else if (inner.style.transform) {
        inner.style.transform = '';
      }
    }
  }

  openEpgModal(key) {
    if (!this.epgItemsMap || !this.epgItemsMap[key]) return;
    const { airing, channel } = this.epgItemsMap[key];
    this.epgCurrentAiring = { airing, channel };

    const modal = document.getElementById('epgDetailModal');
    if (!modal) return;

    document.getElementById('epgModalTitle').textContent = airing.title || channel.name;
    document.getElementById('epgModalChannel').textContent = `${channel.name} • ${channel.network || channel.call_sign} ${channel.resolution ? '(' + channel.resolution + ')' : ''}`;

    const logoEl = document.getElementById('epgModalLogo');
    if (logoEl) {
      if (channel.logo_url) {
        logoEl.src = channel.logo_url;
        logoEl.style.display = 'block';
      } else {
        logoEl.style.display = 'none';
      }
    }

    const durMins = Math.round((airing.duration || 1800) / 60);
    const durStr = durMins >= 60 ? `${Math.floor(durMins / 60)}h ${durMins % 60}m` : `${durMins} mins`;
    document.getElementById('epgModalDuration').textContent = durStr;

    // Time range
    const startStr = new Date(airing.air_datetime).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    const endStr = new Date(new Date(airing.air_datetime).getTime() + (airing.duration || 1800) * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    document.getElementById('epgModalTime').textContent = `${startStr} - ${endStr}`;

    const epTitleEl = document.getElementById('epgModalEpisodeTitle');
    if (epTitleEl) {
      if (airing.episode_title) {
        const epPrefix = airing.season_number ? `S${airing.season_number} E${airing.episode_number}: ` : '';
        epTitleEl.textContent = `${epPrefix}${airing.episode_title}`;
        epTitleEl.style.display = 'block';
      } else {
        epTitleEl.style.display = 'none';
      }
    }

    const descEl = document.getElementById('epgModalDesc');
    if (descEl) {
      descEl.textContent = airing.description || `Broadcast on ${channel.name}. Click "Watch Live Now" to tune in with your Tablo DVR.`;
    }

    const newBadge = document.getElementById('epgModalNewBadge');
    if (newBadge) newBadge.style.display = airing.is_new ? 'inline-block' : 'none';

    const premBadge = document.getElementById('epgModalPremBadge');
    if (premBadge) premBadge.style.display = airing.is_premiere ? 'inline-block' : 'none';

    // Configure watch buttons
    const watchBtn = document.getElementById('epgModalWatchBtn');
    if (watchBtn) {
      watchBtn.onclick = () => {
        this.closeEpgModal();
        this.watchLiveChannel(channel.channel_id, channel.name, airing.title);
      };
    }

    const vlcBtn = document.getElementById('epgModalVlcBtn');
    if (vlcBtn) {
      vlcBtn.onclick = () => {
        this.closeEpgModal();
        this.openLiveInVlc(channel.channel_id);
      };
    }

    modal.classList.add('active');
  }

  closeEpgModal() {
    const modal = document.getElementById('epgDetailModal');
    if (modal) modal.classList.remove('active');
    this.epgCurrentAiring = null;
  }

  async watchLiveChannel(channelId, channelName, showTitle) {
    this.currentLiveChannelId = channelId;
    this.currentWatchEpisodeId = null;

    const modal = document.getElementById('playerModal');
    document.getElementById('playerTitle').textContent = `🔴 Live: ${channelName}`;
    modal.classList.add('active');

    // Sync buffer selector dropdown
    const bufSelect = document.getElementById('playerBufferSelect');
    if (bufSelect) bufSelect.value = String(this.bufferTarget);

    const targetSeconds = this.bufferTarget || 8;
    document.getElementById('playerSubtitle').innerHTML = `<span style="color:#fbbf24; font-weight:600;">⏳ Allocating Tablo tuner & starting live feed (${targetSeconds}s buffer target)...</span>`;

    // Release any stream (and tuner) still held by a previous play
    this.stopCurrentStream();

    try {
      const res = await this.api('/api/live/tune', {
        method: 'POST',
        body: JSON.stringify({ channel_id: channelId, transcode: true })
      });

      this.currentStreamSessionId = res.session_id;

      // Update tuners badge immediately
      this.checkTuners();

      this.startHlsPlayback(res.stream_url, {
        bufferingLabel: 'Buffering live feed',
        playingLabel: '🟢 Live Broadcast',
        steadyLabel: `Live Broadcast (${channelName})`,
        fallbackMs: 8000
      });
    } catch (err) {
      this.showToast(`Live TV tuning error: ${err.message}`, 'error');
      document.getElementById('playerSubtitle').textContent = 'Live tuning failed. Try "Open in VLC".';
      this.checkTuners();
    }
  }

  openLiveInVlc(channelId) {
    const url = `/api/live/vlc/${encodeURIComponent(channelId)}`;
    window.location.href = url;
    this.showToast('Downloaded Live VLC Playlist (.m3u). Opening live broadcast stream in VLC...', 'info');
    setTimeout(() => this.checkTuners(), 2500);
  }
}

// Global App Instance
const app = new TabloApp();
document.addEventListener('DOMContentLoaded', () => app.init());
