"use strict";

// Configuração e estado -----------------------------------------------------

const PAGE_SIZE = 6;

// O estado de cada módulo permanece separado para conservar busca, página e
// seleção quando o usuário alterna entre Salas e Alunos.
const state = {
  active: "rooms",
  rooms: { items: [], selected: null, search: "", status: "", page: 0, baseline: "" },
  students: { items: [], selected: null, search: "", status: "", page: 0, baseline: "" },
};

const elements = {
  toast: document.querySelector("#toast"),
  rooms: {
    module: document.querySelector('[data-module="rooms"]'),
    form: document.querySelector("#room-form"),
    list: document.querySelector("#room-list"),
    search: document.querySelector("#room-search"),
    filters: document.querySelector("#room-filters"),
    count: document.querySelector("#rooms-count"),
    page: document.querySelector("#room-page"),
    title: document.querySelector("#room-form-title"),
    detail: document.querySelector("#room-detail"),
    timestamps: document.querySelector("#room-timestamps"),
    unsaved: document.querySelector("#room-unsaved"),
    save: document.querySelector("#room-save"),
    delete: document.querySelector('[data-action="delete-room"]'),
    previous: document.querySelector('[data-action="previous-rooms"]'),
    next: document.querySelector('[data-action="next-rooms"]'),
  },
  students: {
    module: document.querySelector('[data-module="students"]'),
    form: document.querySelector("#student-form"),
    list: document.querySelector("#student-list"),
    search: document.querySelector("#student-search"),
    filters: document.querySelector("#student-filters"),
    count: document.querySelector("#students-count"),
    page: document.querySelector("#student-page"),
    title: document.querySelector("#student-form-title"),
    detail: document.querySelector("#student-detail"),
    timestamps: document.querySelector("#student-timestamps"),
    unsaved: document.querySelector("#student-unsaved"),
    save: document.querySelector("#student-save"),
    delete: document.querySelector('[data-action="delete-student"]'),
    previous: document.querySelector('[data-action="previous-students"]'),
    next: document.querySelector('[data-action="next-students"]'),
  },
};

let toastTimer;
const searchTimers = {};

// Comunicação com a API ----------------------------------------------------

async function api(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
  });
  let payload = null;
  if (response.status !== 204) {
    payload = await response.json().catch(() => null);
  }
  if (!response.ok) {
    throw new Error(payload?.erro || "Não foi possível concluir a operação.");
  }
  return payload?.dados ?? payload;
}

function notify(message, error = false) {
  clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.toggle("error", error);
  elements.toast.hidden = false;
  toastTimer = setTimeout(() => {
    elements.toast.hidden = true;
  }, 3600);
}

// Controle dos formulários -------------------------------------------------

function formSnapshot(type) {
  const data = new FormData(elements[type].form);
  return JSON.stringify([...data.entries()]);
}

function setBaseline(type) {
  state[type].baseline = formSnapshot(type);
  updateDirty(type);
}

function isDirty(type) {
  return state[type].baseline !== formSnapshot(type);
}

function updateDirty(type) {
  elements[type].unsaved.hidden = !isDirty(type);
}

function canDiscard(type) {
  // O snapshot evita perder alterações ao trocar de registro ou módulo.
  return !isDirty(type) || window.confirm("Existem alterações não salvas. Deseja descartá-las?");
}

function formatDate(value) {
  if (!value) return "";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

function setRadio(form, name, value) {
  const option = form.querySelector(`input[name="${name}"][value="${value}"]`);
  if (option) option.checked = true;
}

function resetRoomForm() {
  const view = elements.rooms;
  state.rooms.selected = null;
  view.form.reset();
  view.title.textContent = "Nova sala";
  view.detail.textContent = "NOVO CADASTRO";
  view.timestamps.textContent = "";
  view.save.textContent = "Criar sala";
  view.delete.disabled = true;
  setBaseline("rooms");
  renderRooms();
}

function fillRoom(room) {
  const view = elements.rooms;
  state.rooms.selected = room;
  view.form.elements.nome.value = room.nome;
  view.form.elements.descricao.value = room.descricao;
  setRadio(view.form, "modo", room.modo);
  setRadio(view.form, "status", room.status);
  view.title.textContent = "Editar sala";
  view.detail.textContent = `CÓDIGO ${room.codigo}`;
  view.timestamps.textContent = `Criada: ${formatDate(room.criada_em)}  •  Editada: ${formatDate(room.atualizada_em)}`;
  view.save.textContent = "Salvar alterações";
  view.delete.disabled = false;
  setBaseline("rooms");
  renderRooms();
}

function resetStudentForm() {
  const view = elements.students;
  state.students.selected = null;
  view.form.reset();
  view.title.textContent = "Novo aluno";
  view.detail.textContent = "NOVO CADASTRO";
  view.timestamps.textContent = "";
  view.save.textContent = "Cadastrar aluno";
  view.delete.disabled = true;
  setBaseline("students");
  renderStudents();
}

function fillStudent(student) {
  const view = elements.students;
  state.students.selected = student;
  view.form.elements.nome.value = student.nome;
  view.form.elements.matricula.value = student.matricula;
  view.form.elements.email.value = student.email;
  setRadio(view.form, "status", student.status);
  view.title.textContent = "Editar aluno";
  view.detail.textContent = `MATRÍCULA ${student.matricula}`;
  view.timestamps.textContent = `Criado: ${formatDate(student.criado_em)}  •  Editado: ${formatDate(student.atualizado_em)}`;
  view.save.textContent = "Salvar alterações";
  view.delete.disabled = false;
  setBaseline("students");
  renderStudents();
}

function recordButton(title, subtitle, status, selected, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `record${selected ? " selected" : ""}`;

  const strong = document.createElement("strong");
  // textContent mantém dados cadastrados como texto, sem interpretar HTML.
  strong.textContent = title;
  const small = document.createElement("small");
  small.textContent = subtitle;
  const badge = document.createElement("span");
  badge.className = `status${["FECHADA", "BLOQUEADO"].includes(status) ? " closed" : ""}`;
  badge.textContent = status;

  button.append(strong, small, badge);
  button.addEventListener("click", onClick);
  return button;
}

function pageValues(type) {
  const info = state[type];
  const totalPages = Math.max(1, Math.ceil(info.items.length / PAGE_SIZE));
  info.page = Math.max(0, Math.min(info.page, totalPages - 1));
  return {
    totalPages,
    rows: info.items.slice(info.page * PAGE_SIZE, (info.page + 1) * PAGE_SIZE),
  };
}

// Renderização das listas --------------------------------------------------

function renderRooms() {
  const info = state.rooms;
  const view = elements.rooms;
  const { rows, totalPages } = pageValues("rooms");
  view.list.replaceChildren();
  view.count.textContent = info.items.length;
  view.page.textContent = `${info.page + 1} / ${totalPages}`;
  view.previous.disabled = info.page === 0;
  view.next.disabled = info.page + 1 >= totalPages;

  if (!rows.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "Nenhuma sala encontrada.";
    view.list.append(empty);
    return;
  }

  rows.forEach((room) => {
    view.list.append(recordButton(
      room.nome,
      `${room.codigo}  |  ${room.modo}`,
      room.status,
      info.selected?.id === room.id,
      () => {
        if (info.selected?.id === room.id || !canDiscard("rooms")) return;
        fillRoom(room);
      },
    ));
  });
}

function renderStudents() {
  const info = state.students;
  const view = elements.students;
  const { rows, totalPages } = pageValues("students");
  view.list.replaceChildren();
  view.count.textContent = info.items.length;
  view.page.textContent = `${info.page + 1} / ${totalPages}`;
  view.previous.disabled = info.page === 0;
  view.next.disabled = info.page + 1 >= totalPages;

  if (!rows.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "Nenhum aluno encontrado.";
    view.list.append(empty);
    return;
  }

  rows.forEach((student) => {
    view.list.append(recordButton(
      student.nome,
      `RA ${student.matricula}  |  ${student.email}`,
      student.status,
      info.selected?.id === student.id,
      () => {
        if (info.selected?.id === student.id || !canDiscard("students")) return;
        fillStudent(student);
      },
    ));
  });
}

// Consultas ao backend -----------------------------------------------------

async function loadRooms(showMessage = false) {
  const info = state.rooms;
  const params = new URLSearchParams();
  if (info.search) params.set("busca", info.search);
  if (info.status) params.set("status", info.status);
  try {
    info.items = await api(`/api/salas?${params}`);
    renderRooms();
    if (showMessage) notify("Lista de salas atualizada.");
  } catch (error) {
    notify(error.message, true);
  }
}

async function loadStudents(showMessage = false) {
  const info = state.students;
  const params = new URLSearchParams();
  if (info.search) params.set("busca", info.search);
  if (info.status) params.set("status", info.status);
  try {
    info.items = await api(`/api/alunos?${params}`);
    renderStudents();
    if (showMessage) notify("Lista de alunos atualizada.");
  } catch (error) {
    notify(error.message, true);
  }
}

// Ações de CRUD ------------------------------------------------------------

function clearRoomFilters() {
  state.rooms.search = "";
  state.rooms.status = "";
  state.rooms.page = 0;
  elements.rooms.search.value = "";
  setActiveFilter("rooms", "");
}

function clearStudentFilters() {
  state.students.search = "";
  state.students.status = "";
  state.students.page = 0;
  elements.students.search.value = "";
  setActiveFilter("students", "");
}

function setActiveFilter(type, status) {
  elements[type].filters.querySelectorAll(".filter").forEach((button) => {
    button.classList.toggle("active", button.dataset.status === status);
  });
}

async function saveRoom(event) {
  event.preventDefault();
  const form = elements.rooms.form;
  const selected = state.rooms.selected;
  const payload = {
    nome: form.elements.nome.value,
    descricao: form.elements.descricao.value,
    modo: form.elements.modo.value,
    status: form.elements.status.value,
  };
  try {
    const room = await api(selected ? `/api/salas/${selected.id}` : "/api/salas", {
      method: selected ? "PUT" : "POST",
      body: JSON.stringify(payload),
    });
    clearRoomFilters();
    await loadRooms();
    fillRoom(room);
    notify(`Sala ${room.codigo} ${selected ? "atualizada" : "criada"} com sucesso.`);
  } catch (error) {
    notify(error.message, true);
  }
}

async function saveStudent(event) {
  event.preventDefault();
  const form = elements.students.form;
  const selected = state.students.selected;
  const payload = {
    nome: form.elements.nome.value,
    matricula: form.elements.matricula.value,
    email: form.elements.email.value,
    status: form.elements.status.value,
  };
  try {
    const student = await api(selected ? `/api/alunos/${selected.id}` : "/api/alunos", {
      method: selected ? "PUT" : "POST",
      body: JSON.stringify(payload),
    });
    clearStudentFilters();
    await loadStudents();
    fillStudent(student);
    notify(`Aluno ${student.matricula} ${selected ? "atualizado" : "cadastrado"} com sucesso.`);
  } catch (error) {
    notify(error.message, true);
  }
}

async function deleteRoom() {
  const room = state.rooms.selected;
  if (!room || !window.confirm(`Excluir a sala “${room.nome}”?`)) return;
  try {
    await api(`/api/salas/${room.id}`, { method: "DELETE" });
    resetRoomForm();
    await loadRooms();
    notify("Sala excluída.");
  } catch (error) {
    notify(error.message, true);
  }
}

async function deleteStudent() {
  const student = state.students.selected;
  if (!student || !window.confirm(`Excluir o aluno “${student.nome}”?`)) return;
  try {
    await api(`/api/alunos/${student.id}`, { method: "DELETE" });
    resetStudentForm();
    await loadStudents();
    notify("Aluno excluído.");
  } catch (error) {
    notify(error.message, true);
  }
}

function switchModule(target) {
  if (target === state.active || !canDiscard(state.active)) return;
  if (state.active === "rooms") {
    state.rooms.selected ? fillRoom(state.rooms.selected) : resetRoomForm();
  } else {
    state.students.selected ? fillStudent(state.students.selected) : resetStudentForm();
  }
  state.active = target;
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.target === target);
  });
  Object.entries(elements).forEach(([name, view]) => {
    if (!["rooms", "students"].includes(name)) return;
    const active = name === target;
    view.module.hidden = !active;
    view.module.classList.toggle("active", active);
  });
}

// Eventos da interface -----------------------------------------------------

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => switchModule(tab.dataset.target));
});

elements.rooms.form.addEventListener("submit", saveRoom);
elements.students.form.addEventListener("submit", saveStudent);
elements.rooms.form.addEventListener("input", () => updateDirty("rooms"));
elements.students.form.addEventListener("input", () => updateDirty("students"));
elements.rooms.form.addEventListener("change", () => updateDirty("rooms"));
elements.students.form.addEventListener("change", () => updateDirty("students"));

elements.rooms.search.addEventListener("input", (event) => {
  clearTimeout(searchTimers.rooms);
  searchTimers.rooms = setTimeout(() => {
    state.rooms.search = event.target.value.trim();
    state.rooms.page = 0;
    loadRooms();
  }, 180);
});

elements.students.search.addEventListener("input", (event) => {
  clearTimeout(searchTimers.students);
  searchTimers.students = setTimeout(() => {
    state.students.search = event.target.value.trim();
    state.students.page = 0;
    loadStudents();
  }, 180);
});

elements.rooms.filters.addEventListener("click", (event) => {
  const button = event.target.closest(".filter");
  if (!button) return;
  state.rooms.status = button.dataset.status;
  state.rooms.page = 0;
  setActiveFilter("rooms", state.rooms.status);
  loadRooms();
});

elements.students.filters.addEventListener("click", (event) => {
  const button = event.target.closest(".filter");
  if (!button) return;
  state.students.status = button.dataset.status;
  state.students.page = 0;
  setActiveFilter("students", state.students.status);
  loadStudents();
});

document.querySelector('[data-action="new-room"]').addEventListener("click", () => {
  if (canDiscard("rooms")) resetRoomForm();
});
document.querySelector('[data-action="new-student"]').addEventListener("click", () => {
  if (canDiscard("students")) resetStudentForm();
});
document.querySelector('[data-action="cancel-room"]').addEventListener("click", () => {
  if (!canDiscard("rooms")) return;
  state.rooms.selected ? fillRoom(state.rooms.selected) : resetRoomForm();
});
document.querySelector('[data-action="cancel-student"]').addEventListener("click", () => {
  if (!canDiscard("students")) return;
  state.students.selected ? fillStudent(state.students.selected) : resetStudentForm();
});
elements.rooms.delete.addEventListener("click", deleteRoom);
elements.students.delete.addEventListener("click", deleteStudent);
document.querySelector('[data-action="refresh-rooms"]').addEventListener("click", () => loadRooms(true));
document.querySelector('[data-action="refresh-students"]').addEventListener("click", () => loadStudents(true));

elements.rooms.previous.addEventListener("click", () => {
  state.rooms.page -= 1;
  renderRooms();
});
elements.rooms.next.addEventListener("click", () => {
  state.rooms.page += 1;
  renderRooms();
});
elements.students.previous.addEventListener("click", () => {
  state.students.page -= 1;
  renderStudents();
});
elements.students.next.addEventListener("click", () => {
  state.students.page += 1;
  renderStudents();
});

window.addEventListener("beforeunload", (event) => {
  // O navegador decide o texto final do aviso por motivos de segurança.
  if (!isDirty("rooms") && !isDirty("students")) return;
  event.preventDefault();
});

document.addEventListener("keydown", (event) => {
  if (event.ctrlKey && event.key.toLowerCase() === "s") {
    event.preventDefault();
    elements[state.active].form.requestSubmit();
  }
  if (event.ctrlKey && event.key.toLowerCase() === "n") {
    event.preventDefault();
    if (!canDiscard(state.active)) return;
    state.active === "rooms" ? resetRoomForm() : resetStudentForm();
  }
  if (event.key === "F5") {
    event.preventDefault();
    state.active === "rooms" ? loadRooms(true) : loadStudents(true);
  }
});

// Inicialização ------------------------------------------------------------

resetRoomForm();
resetStudentForm();
Promise.all([loadRooms(), loadStudents()]);
