import test from 'node:test';
import assert from 'node:assert/strict';
import { ref, reactive, computed } from 'vue';

test('Vue 3 reactivity updates when tasks in upload queue are reactive proxies', () => {
  const queue = ref([]);

  const activeCount = computed(() => {
    return queue.value.filter(t => t.status === 'uploading' || t.status === 'processing' || t.status === 'pending').length;
  });

  const completedCount = computed(() => {
    return queue.value.filter(t => t.status === 'completed').length;
  });

  const headerTitle = computed(() => {
    if (activeCount.value > 0) {
      return `Uploading ${activeCount.value} item...`;
    }
    return `${completedCount.value} upload complete`;
  });

  // Enqueue reactive task
  const task = reactive({
    id: 'test-1',
    name: 'test.pdf',
    size: 5500000,
    progress: 0,
    speed: '0 KB/s',
    status: 'uploading',
  });
  queue.value.push(task);

  assert.equal(activeCount.value, 1);
  assert.equal(headerTitle.value, 'Uploading 1 item...');
  assert.equal(task.progress, 0);

  // Simulate progress event
  task.progress = 50;
  task.speed = '2.5 MB/s';
  assert.equal(task.progress, 50);
  assert.equal(task.speed, '2.5 MB/s');

  // Simulate completion
  task.status = 'completed';
  task.progress = 100;
  task.speed = 'Done';

  assert.equal(activeCount.value, 0);
  assert.equal(completedCount.value, 1);
  assert.equal(headerTitle.value, '1 upload complete');
});

test('AbortController triggers cancellation on active task', () => {
  const abortController = new AbortController();
  const task = reactive({
    id: 'test-2',
    name: 'large_file.zip',
    status: 'uploading',
    abortController,
  });

  assert.equal(task.abortController.signal.aborted, false);
  task.abortController.abort();
  task.status = 'cancelled';

  assert.equal(task.abortController.signal.aborted, true);
  assert.equal(task.status, 'cancelled');
});
