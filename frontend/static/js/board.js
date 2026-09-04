"use strict";

let draggedCard = null;
const selectedTagFilters = new Set();
const allBoardStatuses = ["todo", "in_progress", "blocked", "done", "cancelled"];
let visibleBoardStatuses = new Set(allBoardStatuses);

function boardViewStorageKey() {
  const controls = document.querySelector(".view-system");
  return controls ? `solar-forge-board-view:${controls.dataset.projectId}` : null;
}

function setsMatch(first, second) {
  return first.size === second.size && [...first].every((value) => second.has(value));
}

function loadBoardView() {
  const storageKey = boardViewStorageKey();
  if (!storageKey) {
    return;
  }
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) || "[]");
    const valid = saved.filter((status) => allBoardStatuses.includes(status));
    if (valid.length > 0) {
      visibleBoardStatuses = new Set(valid);
    }
  } catch (_error) {
    visibleBoardStatuses = new Set(allBoardStatuses);
  }
}

function saveBoardView() {
  const storageKey = boardViewStorageKey();
  if (!storageKey) {
    return;
  }
  try {
    localStorage.setItem(storageKey, JSON.stringify([...visibleBoardStatuses]));
  } catch (_error) {
    // The view still works for this session when storage is unavailable.
  }
}

function announceBoardView(message) {
  const announcement = document.querySelector(".view-announcement");
  if (announcement) {
    announcement.textContent = message;
  }
}

function applyBoardView() {
  const board = document.querySelector("#board");
  if (!board) {
    return;
  }
  board.style.setProperty("--visible-columns", String(visibleBoardStatuses.size));
  board.querySelectorAll(".column").forEach((column) => {
    column.hidden = !visibleBoardStatuses.has(column.dataset.status);
  });
  document.querySelectorAll(".lane-toggle").forEach((button) => {
    button.setAttribute(
      "aria-pressed",
      visibleBoardStatuses.has(button.dataset.laneToggle) ? "true" : "false",
    );
  });
  document.querySelectorAll(".view-preset").forEach((button) => {
    const presetStatuses = new Set(button.dataset.viewStatuses.split(","));
    button.setAttribute("aria-pressed", setsMatch(visibleBoardStatuses, presetStatuses) ? "true" : "false");
  });
}

function initializeBoardView() {
  loadBoardView();
  applyBoardView();
}

function allowedStatuses(card) {
  return new Set((card.dataset.allowedStatuses || "").split(",").filter(Boolean));
}

function clearDragState() {
  document.querySelectorAll(".column").forEach((column) => {
    column.classList.remove("is-drop-allowed", "is-drop-target");
  });
  if (draggedCard) {
    draggedCard.classList.remove("is-dragging");
  }
  draggedCard = null;
  document.body.classList.remove("is-dragging-story");
}

function applyTagFilters() {
  document.querySelectorAll(".column").forEach((column) => {
    const cards = [...column.querySelectorAll(".work-card")];
    let visibleCount = 0;
    cards.forEach((card) => {
      const cardTags = new Set((card.dataset.tagIds || "").split(",").filter(Boolean));
      const visible =
        selectedTagFilters.size === 0 ||
        [...selectedTagFilters].some((tagId) => cardTags.has(tagId));
      card.hidden = !visible;
      if (visible) {
        visibleCount += 1;
      }
    });

    const count = column.querySelector(".lane-count");
    if (count) {
      count.textContent = String(visibleCount);
    }
    const filterEmpty = column.querySelector(".column-filter-empty");
    if (filterEmpty) {
      filterEmpty.hidden = selectedTagFilters.size === 0 || cards.length === 0 || visibleCount > 0;
    }
  });

  const clearButton = document.querySelector(".clear-tag-filters");
  if (clearButton) {
    clearButton.hidden = selectedTagFilters.size === 0;
  }
}

document.addEventListener("click", (event) => {
  const presetButton = event.target.closest(".view-preset");
  if (presetButton) {
    visibleBoardStatuses = new Set(presetButton.dataset.viewStatuses.split(","));
    saveBoardView();
    applyBoardView();
    announceBoardView(`${presetButton.textContent.trim()} view selected.`);
    return;
  }

  const laneButton = event.target.closest(".lane-toggle");
  if (laneButton) {
    const status = laneButton.dataset.laneToggle;
    if (visibleBoardStatuses.has(status)) {
      if (visibleBoardStatuses.size === 1) {
        announceBoardView("At least one lane must remain visible.");
        return;
      }
      visibleBoardStatuses.delete(status);
    } else {
      visibleBoardStatuses.add(status);
    }
    saveBoardView();
    applyBoardView();
    announceBoardView(`${visibleBoardStatuses.size} lanes visible. Custom view selected.`);
    return;
  }

  const filterButton = event.target.closest(".tag-filter");
  if (filterButton) {
    const tagId = filterButton.dataset.tagFilter;
    if (selectedTagFilters.has(tagId)) {
      selectedTagFilters.delete(tagId);
      filterButton.setAttribute("aria-pressed", "false");
    } else {
      selectedTagFilters.add(tagId);
      filterButton.setAttribute("aria-pressed", "true");
    }
    applyTagFilters();
    return;
  }

  if (event.target.closest(".clear-tag-filters")) {
    selectedTagFilters.clear();
    document.querySelectorAll(".tag-filter").forEach((button) => {
      button.setAttribute("aria-pressed", "false");
    });
    applyTagFilters();
  }
});

document.addEventListener("htmx:afterSwap", (event) => {
  if (event.target.matches("#board")) {
    applyTagFilters();
    applyBoardView();
  }
});

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initializeBoardView);
} else {
  initializeBoardView();
}

document.addEventListener("dragstart", (event) => {
  const card = event.target.closest(".work-card");
  if (!card || event.target.closest("dialog")) {
    event.preventDefault();
    return;
  }

  draggedCard = card;
  card.classList.add("is-dragging");
  document.body.classList.add("is-dragging-story");
  const allowed = allowedStatuses(card);
  document.querySelectorAll(".column").forEach((column) => {
    if (allowed.has(column.dataset.status)) {
      column.classList.add("is-drop-allowed");
    }
  });

  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setData("text/plain", card.dataset.currentStatus || "story");
});

document.addEventListener("dragover", (event) => {
  const column = event.target.closest(".column");
  if (!draggedCard || !column || !allowedStatuses(draggedCard).has(column.dataset.status)) {
    return;
  }

  event.preventDefault();
  event.dataTransfer.dropEffect = "move";
  document.querySelectorAll(".column.is-drop-target").forEach((candidate) => {
    if (candidate !== column) {
      candidate.classList.remove("is-drop-target");
    }
  });
  column.classList.add("is-drop-target");
});

document.addEventListener("dragleave", (event) => {
  const column = event.target.closest(".column");
  if (column && !column.contains(event.relatedTarget)) {
    column.classList.remove("is-drop-target");
  }
});

document.addEventListener("drop", (event) => {
  const column = event.target.closest(".column");
  const card = draggedCard;
  if (!card || !column || !allowedStatuses(card).has(column.dataset.status)) {
    clearDragState();
    return;
  }

  event.preventDefault();
  const form = card.querySelector(".drag-transition-form");
  const statusInput = form.querySelector('input[name="status"]');
  statusInput.value = column.dataset.status;
  form.requestSubmit();
  clearDragState();
});

document.addEventListener("dragend", clearDragState);
