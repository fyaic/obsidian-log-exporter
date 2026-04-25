const { Plugin, PluginSettingTab, Setting } = require('obsidian');

const STATUS_FILE = '.obsidian/obsidian_log_exporter_status.json';
const EXPORT_FILE = '.obsidian/obsidian_log_export.json';
const PROBE_FILE = '.obsidian/obsidian_log_probe.json';

// Legacy filenames kept for compatibility with downstream tooling.
const LEGACY_STATUS_FILE = '.obsidian/sync_history_plugin_status.json';
const LEGACY_EXPORT_FILE = '.obsidian/sync_history_export.json';
const LEGACY_PROBE_FILE = '.obsidian/sync_history_probe.json';

// Debounce delay for real-time export (ms)
const DEBOUNCE_MS = 3000;

module.exports = class ObsidianLogExporter extends Plugin {
    async onload() {
        console.log("[ObsidianLogExporter] Plugin loaded, waiting for metadata sources...");
        await this.writeStatus("loaded", {
            plugin_version: "realtime-v1"
        });
        
        this.debounceTimer = null;
        this.syncReady = false;
        this.fileEventsRegistered = false;
        
        this.addCommand({
            id: 'run-obsidian-log-export',
            name: 'Run Obsidian Log Export',
            callback: async () => {
                await this.writeStatus("command_invoked");
                try {
                    await this.runDeepProbe();
                    await this.writeStatus("command_completed");
                } catch (e) {
                    await this.writeStatus("command_failed", { error: e.message });
                    throw e;
                }
            }
        });

        // Wait for Sync to initialize, then run initial export + register listeners
        this.waitForSyncAndProbe();

        this.addSettingTab(new ObsidianLogExporterSettingTab(this.app, this));
    }

    async writeStatus(stage, extra = {}) {
        const payload = {
            ts: new Date().toISOString(),
            stage,
            vault: this.app.vault.getName(),
            plugin_id: this.manifest.id,
            ...extra
        };
        const content = JSON.stringify(payload, null, 2);
        await this.app.vault.adapter.write(STATUS_FILE, content);
        await this.app.vault.adapter.write(LEGACY_STATUS_FILE, content);
    }

    async waitForSyncAndProbe() {
        const maxWait = 60; // seconds
        const interval = 3; // seconds
        let waited = 0;
        
        while (waited < maxWait) {
            const syncPlugin = this.app.internalPlugins.plugins.sync;
            if (syncPlugin && syncPlugin.instance) {
                const inst = syncPlugin.instance;
                console.log(`[ObsidianLogExporter] Sync state: initialized=${inst.initialized}, ready=${inst.ready}, deviceName=${inst.deviceName}`);
                await this.writeStatus("waiting_for_sync", {
                    waited_seconds: waited,
                    initialized: !!inst.initialized,
                    ready: !!inst.ready,
                    deviceName: inst.deviceName || null
                });
                
                if (inst.initialized && inst.ready) {
                    console.log("[ObsidianLogExporter] Sync is ready. Running initial export...");
                    // Silent: no notice
                    this.syncReady = true;
                    await this.runDeepProbe();
                    this.registerFileEvents();
                    return;
                }
            }
            
            await new Promise(r => setTimeout(r, interval * 1000));
            waited += interval;
        }
        
        console.log("[ObsidianLogExporter] Sync not ready after 60s, exporting with partial data...");
        // Silent: no notice
        await this.writeStatus("sync_wait_timeout", { waited_seconds: waited });
        await this.runDeepProbe();
        this.registerFileEvents();
    }

    registerFileEvents() {
        if (this.fileEventsRegistered) return;
        this.fileEventsRegistered = true;
        
        console.log("[ObsidianLogExporter] Registering real-time file event listeners...");
        
        const debouncedExport = () => {
            if (this.debounceTimer) clearTimeout(this.debounceTimer);
            this.debounceTimer = setTimeout(async () => {
                console.log("[ObsidianLogExporter] File change detected, re-exporting...");
                await this.writeStatus("realtime_triggered");
                try {
                    await this.runDeepProbe();
                } catch (e) {
                    console.error("[ObsidianLogExporter] Real-time export failed:", e);
                }
            }, DEBOUNCE_MS);
        };
        
        // Listen to all vault file changes
        this.registerEvent(this.app.vault.on('create', debouncedExport));
        this.registerEvent(this.app.vault.on('modify', debouncedExport));
        this.registerEvent(this.app.vault.on('delete', debouncedExport));
        this.registerEvent(this.app.vault.on('rename', debouncedExport));
        
        console.log("[ObsidianLogExporter] Real-time listeners active.");
    }

    async runDeepProbe() {
        await this.writeStatus("probe_started");
        const result = {
            exported_at: new Date().toISOString(),
            this_device: {},
            usernames: null,
            server_files: [],
            all_sync_history: {},
            metadata_cache_with_author: [],
            file_recovery_stats: {},
            folder_file_counts: {}
        };

        // === 1. Read this device's info from Sync ===
        try {
            const syncPlugin = this.app.internalPlugins.plugins.sync;
            if (syncPlugin && syncPlugin.instance) {
                const inst = syncPlugin.instance;
                result.this_device = {
                    deviceName: inst.deviceName || null,
                    userId: inst.userId || null,
                    vaultId: inst.vaultId || null,
                    vaultName: inst.vaultName || null,
                    version: inst.version || null,
                    host: inst.host || null,
                    initialized: inst.initialized || false,
                    ready: inst.ready || false,
                    syncing: inst.syncing || false,
                    server: inst.server ? {
                        url: inst.server.url || null,
                        status: inst.server.status || null
                    } : null
                };

                // Try getUsernames
                try {
                    if (typeof inst.getUsernames === 'function') {
                        result.usernames = await inst.getUsernames();
                    }
                } catch(e) {
                    result.usernames_error = e.message;
                }

                // Export the server-side file index used by Sync UI and recent changes UI.
                try {
                    const usernameMap = result.usernames || {};
                    const serverFiles = Object.values(inst.serverFiles || {});
                    result.server_files = serverFiles.map(file => ({
                        path: file.path || "",
                        mtime: file.mtime || 0,
                        size: file.size || 0,
                        deleted: !!file.deleted,
                        folder: !!file.folder,
                        device: file.device || "",
                        user: file.user ?? null,
                        username: file.user != null ? (usernameMap[String(file.user)] || "") : "",
                        hash: file.hash || ""
                    }));
                } catch(e) {
                    result.server_files_error = e.message;
                }

                await this.writeStatus("sync_snapshot_ready", {
                    server_files: result.server_files.length
                });

                // Try getDefaultDeviceName
                try {
                    if (typeof inst.getDefaultDeviceName === 'function') {
                        result.default_device_name = await inst.getDefaultDeviceName();
                    }
                } catch(e) {
                    result.default_device_name_error = e.message;
                }

                // Try getHistory on a small sample only. Full-vault iteration can hang.
                const sampleFiles = this.app.vault.getMarkdownFiles().slice(0, 20);
                result.history_sample_size = sampleFiles.length;
                await this.writeStatus("history_sampling_started", {
                    sample_size: sampleFiles.length
                });
                for (const file of sampleFiles) {
                    try {
                        const hist = await Promise.race([
                            inst.getHistory(file.path),
                            new Promise((_, reject) => setTimeout(() => reject(new Error("getHistory timeout")), 1500))
                        ]);
                        if (hist && hist.length > 0) {
                            result.all_sync_history[file.path] = hist;
                        }
                    } catch(e) {
                        if (!result.history_sample_errors) {
                            result.history_sample_errors = [];
                        }
                        result.history_sample_errors.push({
                            path: file.path,
                            error: e.message
                        });
                    }
                }
                await this.writeStatus("history_sampling_finished", {
                    history_files: Object.keys(result.all_sync_history).length
                });
            } else {
                result.sync_plugin_missing = true;
            }
        } catch(e) {
            result.sync_error = e.message;
        }

        // === 2. Scan ALL metadataCache for author frontmatter ===
        try {
            const allFiles = this.app.vault.getMarkdownFiles();
            for (const file of allFiles) {
                const cache = this.app.metadataCache.getFileCache(file);
                if (cache && cache.frontmatter) {
                    const fm = cache.frontmatter;
                    if (fm.author) {
                        result.metadata_cache_with_author.push({
                            path: file.path,
                            author: fm.author
                        });
                    }
                }
            }
        } catch(e) {
            result.metadata_error = e.message;
        }

        // === 3. File Recovery stats ===
        try {
            const frPlugin = this.app.internalPlugins.plugins['file-recovery'];
            if (frPlugin && frPlugin.instance && frPlugin.instance.db) {
                const db = frPlugin.instance.db;
                const tx = db.transaction('backups');
                const all = await tx.store.getAll();
                result.file_recovery_stats = {
                    total_backups: all.length,
                    unique_files: [...new Set(all.map(x => x.path))].length,
                    date_range: {
                        oldest: all.length > 0 ? Math.min(...all.map(x => x.ts)) : null,
                        newest: all.length > 0 ? Math.max(...all.map(x => x.ts)) : null
                    }
                };
            }
        } catch(e) {
            result.file_recovery_error = e.message;
        }

        // === 4. Folder-level file counts ===
        try {
            const allFiles = this.app.vault.getMarkdownFiles();
            const counts = {};
            for (const file of allFiles) {
                const folder = file.parent?.path || '(root)';
                counts[folder] = (counts[folder] || 0) + 1;
            }
            result.folder_file_counts = Object.entries(counts)
                .sort((a, b) => b[1] - a[1])
                .reduce((obj, [k, v]) => { obj[k] = v; return obj; }, {});
        } catch(e) {}

        // Write a verbose probe plus a concise export for agents/tooling.
        const exportPayload = {
            exported_at: result.exported_at,
            this_device: result.this_device,
            usernames: result.usernames,
            server_files: result.server_files,
            sync_history: Object.entries(result.all_sync_history).map(([path, versions]) => ({
                path,
                versions
            }))
        };

        const probeContent = JSON.stringify(result, null, 2);
        const exportContent = JSON.stringify(exportPayload, null, 2);
        await this.app.vault.adapter.write(PROBE_FILE, probeContent);
        await this.app.vault.adapter.write(EXPORT_FILE, exportContent);
        await this.app.vault.adapter.write(LEGACY_PROBE_FILE, probeContent);
        await this.app.vault.adapter.write(LEGACY_EXPORT_FILE, exportContent);

        await this.writeStatus("probe_written", {
            server_files: result.server_files.length,
            history_files: Object.keys(result.all_sync_history).length
        });
        const msg = `Log export done. deviceName=${result.this_device.deviceName}, server_files=${result.server_files.length}, history_files=${Object.keys(result.all_sync_history).length}`;
        console.log(`[ObsidianLogExporter] ${msg}`);
        // Silent: no notice
    }

    async healthCheck() {
        const checks = [];
        let ok = true;

        // 1. Plugin instance alive
        checks.push({ name: 'Plugin instance', pass: true, detail: 'this is defined' });

        // 2. Vault adapter writable (real IO)
        try {
            const testPath = '.obsidian/.obsidian_log_exporter_health';
            await this.app.vault.adapter.write(testPath, '{"health":true}');
            const readBack = await this.app.vault.adapter.read(testPath);
            const parsed = JSON.parse(readBack);
            if (parsed.health === true) {
                checks.push({ name: 'Vault IO (write/read)', pass: true, detail: 'read/write OK' });
            } else {
                checks.push({ name: 'Vault IO (write/read)', pass: false, detail: 'readback mismatch' });
                ok = false;
            }
            await this.app.vault.adapter.remove(testPath).catch(() => {});
        } catch (e) {
            checks.push({ name: 'Vault IO (write/read)', pass: false, detail: e.message });
            ok = false;
        }

        // 3. Sync plugin state
        try {
            const syncPlugin = this.app.internalPlugins.plugins.sync;
            if (syncPlugin && syncPlugin.instance) {
                const inst = syncPlugin.instance;
                const state = `initialized=${inst.initialized}, ready=${inst.ready}, deviceName=${inst.deviceName || 'null'}`;
                checks.push({ name: 'Sync plugin', pass: !!inst.ready, detail: state });
                if (!inst.ready) ok = false;
            } else {
                checks.push({ name: 'Sync plugin', pass: false, detail: 'not found' });
                ok = false;
            }
        } catch (e) {
            checks.push({ name: 'Sync plugin', pass: false, detail: e.message });
            ok = false;
        }

        // 4. File event listeners registered
        checks.push({ name: 'Realtime listeners', pass: this.fileEventsRegistered, detail: `registered=${this.fileEventsRegistered}` });
        if (!this.fileEventsRegistered) ok = false;

        // 5. Status file readable and recent
        try {
            const raw = await this.app.vault.adapter.read(STATUS_FILE);
            const status = JSON.parse(raw);
            const ageSec = (Date.now() - new Date(status.ts).getTime()) / 1000;
            const recent = ageSec < 300; // within 5 min
            checks.push({ name: 'Last status file', pass: recent, detail: `stage=${status.stage}, age=${Math.round(ageSec)}s` });
            if (!recent) ok = false;
        } catch (e) {
            checks.push({ name: 'Last status file', pass: false, detail: e.message });
            ok = false;
        }

        // 6. Export file exists and valid JSON
        try {
            const raw = await this.app.vault.adapter.read(EXPORT_FILE);
            const exported = JSON.parse(raw);
            const hasData = Array.isArray(exported.server_files);
            checks.push({ name: 'Export file', pass: hasData, detail: `server_files=${hasData ? exported.server_files.length : 'N/A'}` });
            if (!hasData) ok = false;
        } catch (e) {
            checks.push({ name: 'Export file', pass: false, detail: e.message });
            ok = false;
        }

        return { ok, checks };
    }

    onunload() {
        if (this.debounceTimer) clearTimeout(this.debounceTimer);
        console.log("[ObsidianLogExporter] Plugin unloaded");
    }
};

class ObsidianLogExporterSettingTab extends PluginSettingTab {
    constructor(app, plugin) {
        super(app, plugin);
        this.plugin = plugin;
    }

    display() {
        const { containerEl } = this;
        containerEl.empty();
        containerEl.createEl('h2', { text: 'Obsidian Log Exporter' });

        let resultBox = null;

        new Setting(containerEl)
            .setName('Health Check')
            .setDesc('Run a real check: vault IO, sync state, listeners, export integrity.')
            .addButton(btn => btn
                .setButtonText('Verify')
                .onClick(async () => {
                    btn.setDisabled(true);
                    btn.setButtonText('Checking...');
                    try {
                        const health = await this.plugin.healthCheck();
                        if (resultBox) resultBox.remove();
                        resultBox = containerEl.createDiv();
                        resultBox.style.marginTop = '12px';

                        const summary = resultBox.createEl('div', {
                            text: health.ok ? 'All checks passed.' : 'Some checks failed.',
                        });
                        summary.style.fontWeight = 'bold';
                        summary.style.marginBottom = '8px';
                        summary.style.color = health.ok ? 'var(--text-success)' : 'var(--text-error)';

                        const list = resultBox.createEl('ul');
                        list.style.paddingLeft = '20px';
                        list.style.margin = '0';
                        for (const c of health.checks) {
                            const li = list.createEl('li');
                            li.style.marginBottom = '4px';
                            const mark = c.pass ? '✅' : '❌';
                            li.createEl('span', { text: `${mark} ${c.name}: ` });
                            const detail = li.createEl('span', { text: c.detail });
                            detail.style.color = 'var(--text-muted)';
                            detail.style.fontSize = '0.9em';
                        }
                    } finally {
                        btn.setDisabled(false);
                        btn.setButtonText('Verify');
                    }
                }));
    }
}
