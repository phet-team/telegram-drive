import { ref, onMounted, onUnmounted } from 'vue';
import { useDriveStore } from '../stores/drive';

export function useMarqueeSelection(containerRef) {
  const drive = useDriveStore();
  const isDragging = ref(false);
  const selectionBox = ref(null);

  let startX = 0;
  let startY = 0;
  let hasMoved = false;

  const handleMouseDown = (e) => {
    // Only primary (left) button
    if (e.button !== 0) return;

    // Check if clicked inside an interactive element or item card
    const target = e.target;
    if (
      target.closest('button') ||
      target.closest('input') ||
      target.closest('a') ||
      target.closest('[data-selectable-id]')
    ) {
      return;
    }

    if (!containerRef.value) return;

    const containerRect = containerRef.value.getBoundingClientRect();
    startX = e.clientX - containerRect.left + containerRef.value.scrollLeft;
    startY = e.clientY - containerRect.top + containerRef.value.scrollTop;
    hasMoved = false;

    // Clear selection if clicking empty background without Ctrl/Shift
    if (!e.ctrlKey && !e.metaKey && !e.shiftKey) {
      drive.clearSelection();
    }

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  };

  const handleMouseMove = (e) => {
    if (!containerRef.value) return;

    const containerRect = containerRef.value.getBoundingClientRect();
    const currentX = e.clientX - containerRect.left + containerRef.value.scrollLeft;
    const currentY = e.clientY - containerRect.top + containerRef.value.scrollTop;

    const dx = Math.abs(currentX - startX);
    const dy = Math.abs(currentY - startY);

    if (dx > 4 || dy > 4) {
      hasMoved = true;
      isDragging.value = true;
    }

    if (!isDragging.value) return;

    const left = Math.min(startX, currentX);
    const top = Math.min(startY, currentY);
    const width = Math.abs(currentX - startX);
    const height = Math.abs(currentY - startY);

    selectionBox.value = { left, top, width, height };

    // Find all items currently intersecting the marquee box
    const selectableElements = containerRef.value.querySelectorAll('[data-selectable-id]');
    const intersectingIds = new Set();

    const boxRect = {
      left,
      right: left + width,
      top,
      bottom: top + height,
    };

    selectableElements.forEach((el) => {
      const elRect = {
        left: el.offsetLeft,
        right: el.offsetLeft + el.offsetWidth,
        top: el.offsetTop,
        bottom: el.offsetTop + el.offsetHeight,
      };

      // Check AABB intersection
      const intersects =
        boxRect.left <= elRect.right &&
        boxRect.right >= elRect.left &&
        boxRect.top <= elRect.bottom &&
        boxRect.bottom >= elRect.top;

      if (intersects) {
        intersectingIds.add(el.getAttribute('data-selectable-id'));
      }
    });

    // Update store selectedItems
    const allItems = [
      ...drive.folders.map(f => ({ ...f, type: 'folder' })),
      ...drive.files.map(f => ({ ...f, type: 'file' })),
    ];

    const matched = allItems.filter(i => intersectingIds.has(i.id));
    drive.selectedItems = matched;
  };

  const handleMouseUp = () => {
    window.removeEventListener('mousemove', handleMouseMove);
    window.removeEventListener('mouseup', handleMouseUp);

    isDragging.value = false;
    selectionBox.value = null;
  };

  onMounted(() => {
    if (containerRef.value) {
      containerRef.value.addEventListener('mousedown', handleMouseDown);
    }
  });

  onUnmounted(() => {
    if (containerRef.value) {
      containerRef.value.removeEventListener('mousedown', handleMouseDown);
    }
    window.removeEventListener('mousemove', handleMouseMove);
    window.removeEventListener('mouseup', handleMouseUp);
  });

  return {
    isDragging,
    selectionBox,
  };
}
