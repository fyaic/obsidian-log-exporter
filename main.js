const { Plugin, Notice } = require('obsidian');

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
                    new Notice("Obsidian Log Exporter: Sync ready, exporting logs...");
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
        new Notice("Obsidian Log Exporter: Sync not ready after 60s, exporting partial data...");
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
        new Notice(msg);
    }

    onunload() {
        if (this.debounceTimer) clearTimeout(this.debounceTimer);
        console.log("[ObsidianLogExporter] Plugin unloaded");
    }
};
