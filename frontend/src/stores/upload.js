import { defineStore } from 'pinia';
import { ref, reactive } from 'vue';
import api from '../services/api';
import { useFeedbackStore } from './feedback';
import { useDriveStore } from './drive';
import { useAuthStore } from './auth';

const envChunkMb = Number(import.meta.env.VITE_CHUNK_SIZE_MB);
const CHUNK_SIZE = (!isNaN(envChunkMb) && envChunkMb > 0 ? envChunkMb : 8) * 1024 * 1024;

export const useUploadStore = defineStore('upload', () => {
  const queue = ref([]);
  const conflictQueue = ref([]);
  const isDrawerOpen = ref(false);
  const isMinimized = ref(false);

  const feedback = useFeedbackStore();
  const drive = useDriveStore();
  const auth = useAuthStore();

  const getAvailableName = (originalName, existingNames) => {
    const lastDot = originalName.lastIndexOf('.');
    const baseName = lastDot !== -1 ? originalName.slice(0, lastDot) : originalName;
    const ext = lastDot !== -1 ? originalName.slice(lastDot) : '';

    let counter = 1;
    let newName = `${baseName} (${counter})${ext}`;
    while (existingNames.has(newName.toLowerCase())) {
      counter++;
      newName = `${baseName} (${counter})${ext}`;
    }
    return newName;
  };

  const enqueueSingleTask = (file, folderId, overrideName = null, replaceFileId = null) => {
    isDrawerOpen.value = true;
    isMinimized.value = false;

    const taskName = overrideName || file.name;
    const abortController = new AbortController();
    const task = reactive({
      id: `${Date.now()}_${Math.random().toString(36).substring(2, 9)}`,
      file,
      name: taskName,
      size: file.size,
      progress: 0,
      speed: '0 KB/s',
      status: 'pending', // 'pending' | 'uploading' | 'paused' | 'processing' | 'completed' | 'failed' | 'cancelled'
      folderId,
      sessionId: null,
      replaceFileId,
      abortController,
      error: null,
    });
    queue.value.push(task);
    startUpload(task);
  };

  const enqueueFiles = (fileList, folderId = null) => {
    const currentFiles = drive.files.filter(f => !f.is_trashed);
    const existingFileMap = new Map();
    for (const f of currentFiles) {
      existingFileMap.set(f.name.toLowerCase(), f);
    }

    const nonConflicting = [];

    for (const file of fileList) {
      const existing = existingFileMap.get(file.name.toLowerCase());
      if (existing) {
        conflictQueue.value.push({
          file,
          folderId,
          existingFile: existing,
        });
      } else {
        nonConflicting.push(file);
        existingFileMap.set(file.name.toLowerCase(), { name: file.name, size: file.size });
      }
    }

    for (const file of nonConflicting) {
      enqueueSingleTask(file, folderId);
    }
  };

  const resolveConflict = (action, applyToAll = false) => {
    if (conflictQueue.value.length === 0) return;

    const count = applyToAll ? conflictQueue.value.length : 1;
    const itemsToResolve = conflictQueue.value.splice(0, count);

    const existingNames = new Set(drive.files.filter(f => !f.is_trashed).map(f => f.name.toLowerCase()));
    for (const t of queue.value) {
      existingNames.add(t.name.toLowerCase());
    }

    for (const item of itemsToResolve) {
      if (action === 'replace') {
        enqueueSingleTask(item.file, item.folderId, item.file.name, item.existingFile.id);
      } else if (action === 'keepBoth') {
        const newName = getAvailableName(item.file.name, existingNames);
        existingNames.add(newName.toLowerCase());
        enqueueSingleTask(item.file, item.folderId, newName, null);
      }
      // 'skip' cancels uploading this file
    }
  };

  const startUpload = async (task) => {
    task.status = 'uploading';
    task.error = null;
    let sessionId = task.sessionId;
    let chunkSize = CHUNK_SIZE;
    let totalChunks = Math.max(1, Math.ceil(task.size / chunkSize));
    let alreadyUploadedSet = new Set();

    try {
      // Step 1: Check if an existing session can be resumed
      if (sessionId) {
        try {
          const sessionRes = await api.get(`/drive/uploads/${sessionId}/`, {
            signal: task.abortController?.signal,
          });
          if (sessionRes.data && sessionRes.data.status === 'UPLOADING' && !sessionRes.data.is_expired) {
            chunkSize = sessionRes.data.chunk_size || CHUNK_SIZE;
            totalChunks = sessionRes.data.total_chunks;
            alreadyUploadedSet = new Set(sessionRes.data.uploaded_chunks || []);
          } else {
            sessionId = null;
          }
        } catch (e) {
          sessionId = null;
        }
      }

      // If no valid session to resume, initiate a fresh upload session
      if (!sessionId) {
        const initRes = await api.post('/drive/uploads/initiate/', {
          filename: task.name,
          total_size: task.size,
          chunk_size: CHUNK_SIZE,
          mime_type: task.file.type || 'application/octet-stream',
          folder_id: task.folderId,
        }, {
          signal: task.abortController?.signal,
        });
        sessionId = initRes.data.session_id;
        chunkSize = initRes.data.chunk_size || CHUNK_SIZE;
        totalChunks = initRes.data.total_chunks;
        task.sessionId = sessionId;
      }

      // Initialize chunk progress based on already uploaded chunks
      const chunkLoaded = new Array(totalChunks).fill(0);
      for (let i = 0; i < totalChunks; i++) {
        if (alreadyUploadedSet.has(i)) {
          const start = i * chunkSize;
          const end = Math.min(task.size, start + chunkSize);
          chunkLoaded[i] = end - start;
        }
      }

      const initialTotal = chunkLoaded.reduce((a, b) => a + b, 0);
      task.progress = Math.min(99, Math.round((initialTotal / (task.size || 1)) * 100));
      task.chunkStatus = `${alreadyUploadedSet.size}/${totalChunks}`;

      const startTime = Date.now();
      const CONCURRENCY = 3;
      let nextChunkIdx = 0;

      const updateProgress = () => {
        const currentTotal = chunkLoaded.reduce((a, b) => a + b, 0);
        const pct = Math.min(99, Math.round((currentTotal / (task.size || 1)) * 100));
        task.progress = pct;
        task.chunkStatus = `${alreadyUploadedSet.size}/${totalChunks}`;

        const elapsedSec = (Date.now() - startTime) / 1000;
        if (elapsedSec > 0.5) {
          const speedBytes = (currentTotal - initialTotal) / elapsedSec;
          if (speedBytes >= 1024 * 1024) {
            task.speed = `${(speedBytes / (1024 * 1024)).toFixed(1)} MB/s`;
          } else if (speedBytes > 0) {
            task.speed = `${Math.round(speedBytes / 1024)} KB/s`;
          }
        }
      };

      // Step 2: Concurrently upload remaining chunks
      const uploadWorker = async () => {
        while (nextChunkIdx < totalChunks) {
          if (task.abortController?.signal?.aborted) {
            throw new Error('Upload aborted');
          }

          const i = nextChunkIdx++;
          // Skip chunks that were already uploaded successfully
          if (alreadyUploadedSet.has(i)) {
            continue;
          }

          const start = i * chunkSize;
          const end = Math.min(task.size, start + chunkSize);
          const chunkBlob = task.file.slice(start, end);

          // Retry logic (up to 2 retries per chunk for transient network hiccups)
          let retries = 2;
          while (retries >= 0) {
            try {
              await api.put(`/drive/uploads/${sessionId}/chunks/${i}/`, chunkBlob, {
                headers: {
                  'Content-Type': 'application/octet-stream',
                },
                signal: task.abortController?.signal,
                onUploadProgress: (progressEvent) => {
                  const ratio = progressEvent.total ? (progressEvent.loaded / progressEvent.total) : 0;
                  // Browser->VPS is 25% of chunk journey; VPS->Telegram is the remaining 75%
                  chunkLoaded[i] = (chunkBlob.size * 0.25) * ratio;
                  updateProgress();
                },
              });
              // Confirmed stored in Telegram
              chunkLoaded[i] = chunkBlob.size;
              alreadyUploadedSet.add(i);
              updateProgress();
              break;
            } catch (err) {
              if (task.abortController?.signal?.aborted) throw err;
              if (retries === 0) throw err;
              retries--;
              await new Promise((r) => setTimeout(r, 1000));
            }
          }
        }
      };

      const workerCount = Math.min(CONCURRENCY, totalChunks);
      const workers = Array.from({ length: workerCount }, () => uploadWorker());
      await Promise.all(workers);

      // Step 3: Complete upload session (Finalize on cloud/Telegram)
      task.status = 'processing';
      task.speed = 'Finalizing...';
      task.progress = 100;

      await api.post(`/drive/uploads/${sessionId}/complete/`, {
        replace_file_id: task.replaceFileId || undefined,
      }, {
        signal: task.abortController?.signal,
      });

      task.status = 'completed';
      task.speed = 'Done';
      task.progress = 100;
      feedback.showToast('success', `"${task.name}" uploaded successfully`);

      // Refresh drive contents silently only if viewing target folder in My Drive
      if (drive.currentSection === 'drive' && (drive.currentFolder?.id || null) === (task.folderId || null)) {
        drive.fetchContents(drive.currentFolder?.id, true);
      }
      auth.fetchMe();
    } catch (err) {
      if (task.status === 'paused') {
        task.speed = 'Paused';
        return;
      }
      if (err.name === 'CanceledError' || err.message === 'Upload aborted' || task.status === 'cancelled') {
        task.status = 'cancelled';
        task.speed = 'Cancelled';
        return;
      }
      task.status = 'failed';
      task.speed = 'Failed';
      const msg = err.response?.data?.[0] || err.response?.data?.detail || err.message || 'Upload failed';
      task.error = msg;
      feedback.showToast('error', `${task.name}: ${msg}`);
    }
  };

  const pauseUpload = (taskId) => {
    const task = queue.value.find(t => t.id === taskId);
    if (!task || task.status !== 'uploading') return;
    task.status = 'paused';
    task.speed = 'Paused';
    if (task.abortController) {
      task.abortController.abort();
    }
  };

  const resumeUpload = (taskId) => {
    const task = queue.value.find(t => t.id === taskId);
    if (!task || (task.status !== 'paused' && task.status !== 'failed')) return;
    task.abortController = new AbortController();
    task.status = 'uploading';
    task.speed = 'Resuming...';
    task.error = null;
    startUpload(task);
  };

  const cancelUpload = async (taskId) => {
    const task = queue.value.find(t => t.id === taskId);
    if (!task) return;

    if (task.status === 'uploading' || task.status === 'pending' || task.status === 'processing' || task.status === 'paused') {
      task.status = 'cancelled';
      task.speed = 'Cancelled';
      if (task.abortController) {
        task.abortController.abort();
      }
      if (task.sessionId) {
        try {
          await api.post(`/drive/uploads/${task.sessionId}/cancel/`);
        } catch (e) {
          // ignore error on cancellation
        }
      }
    }
  };

  const retryUpload = (taskId) => {
    resumeUpload(taskId);
  };

  const removeTask = (taskId) => {
    cancelUpload(taskId);
    queue.value = queue.value.filter(t => t.id !== taskId);
    if (queue.value.length === 0) {
      isDrawerOpen.value = false;
    }
  };

  const clearCompleted = () => {
    queue.value = queue.value.filter(t => t.status !== 'completed' && t.status !== 'cancelled');
    if (queue.value.length === 0) {
      isDrawerOpen.value = false;
    }
  };

  return {
    queue,
    conflictQueue,
    isDrawerOpen,
    isMinimized,
    enqueueFiles,
    resolveConflict,
    startUpload,
    pauseUpload,
    resumeUpload,
    cancelUpload,
    retryUpload,
    removeTask,
    clearCompleted,
  };
});

