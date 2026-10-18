"use strict";

const assert = require("node:assert/strict");
const { test } = require("node:test");
const { factualAppointmentResponse, toolCallsAndAppointments } = require("./assertions.js");

function context(metadata, vars = {}) {
  return { providerResponse: { metadata }, vars };
}

const validMetadata = {
  tool_calls: [
    { order: 1, name: "calendarizar_cita", origin: "agent:SupervisorCentral", arguments: { input: "2026-10-01" }, error: null },
    { order: 2, name: "schedule_tool", origin: "agent:CalendarWorker", arguments: { date: "2026-10-01" }, error: null },
  ],
  appointments: {
    initial: [],
    final: [{ date: "2026-10-01", status: "pending" }],
    created: [{ date: "2026-10-01", status: "pending" }],
  },
};

test("acepta herramientas, argumentos, origen, secuencia y persistencia válidos", () => {
  const result = toolCallsAndAppointments(
    "La cita fue calendarizada tentativamente.",
    context(validMetadata, {
      required_tools: [
        { name: "calendarizar_cita", origin: "agent:SupervisorCentral", arguments: { input: "2026-10-01" } },
        { name: "schedule_tool", origin: "agent:CalendarWorker", arguments: { date: "2026-10-01" } },
      ],
      expected_sequence: ["calendarizar_cita", "schedule_tool"],
      expected_created_appointments: 1,
    }),
  );
  assert.equal(result.pass, true);
});

test("falla si los argumentos de una llamada son incorrectos", () => {
  const result = toolCallsAndAppointments("", context(validMetadata, {
    required_tools: [{ name: "schedule_tool", origin: "agent:CalendarWorker", arguments: { date: "2026-10-02" } }],
  }));
  assert.equal(result.pass, false);
  assert.match(result.reason, /Falta llamada requerida/);
});

test("falla si falta una herramienta requerida", () => {
  const result = toolCallsAndAppointments("", context(validMetadata, {
    required_tools: ["weather_tool"],
  }));
  assert.equal(result.pass, false);
  assert.match(result.reason, /Falta llamada requerida/);
});

test("falla una confirmación sin cita persistida", () => {
  const metadata = {
    tool_calls: [{ order: 1, name: "calendarizar_cita", origin: "agent:SupervisorCentral", arguments: {}, error: null }],
    appointments: { initial: [], final: [], created: [] },
  };
  const result = toolCallsAndAppointments("La cita fue calendarizada.", context(metadata));
  assert.equal(result.pass, false);
  assert.match(result.reason, /no hay una cita persistida/);
});

test("falla si no existe evidencia de herramientas", () => {
  const result = toolCallsAndAppointments("La cita fue calendarizada.", context({ appointments: { created: [] } }));
  assert.equal(result.pass, false);
  assert.match(result.reason, /metadata.tool_calls/);
});

test("comprueba factualidad de una cita persistida sin juez remoto", () => {
  const result = factualAppointmentResponse(
    "La cita fue calendarizada tentativamente.",
    context(validMetadata, { reference: "La cita se calendariza tentativamente." }),
  );
  assert.equal(result.pass, true);
});

test("falla si una cita rechazada se presenta como confirmada", () => {
  const metadata = { ...validMetadata, appointments: { initial: [], final: [], created: [] } };
  const result = factualAppointmentResponse(
    "La cita fue calendarizada.",
    context(metadata, { reference: "La cita no se calendariza porque el clima es inseguro." }),
  );
  assert.equal(result.pass, false);
  assert.match(result.reason, /no fue persistida/);
});
