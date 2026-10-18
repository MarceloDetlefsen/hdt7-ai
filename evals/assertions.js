"use strict";

/**
 * Assertion reutilizable para evidencia de herramientas y persistencia.
 * Compatible con Promptfoo 0.123.1: (output, assertionContext).
 */

function parseVar(value, fallback) {
  if (value === undefined || value === null || value === "") return fallback;
  if (Array.isArray(value) || typeof value === "object") return value;
  return JSON.parse(value);
}

function matchesValue(actual, expected) {
  if (expected === undefined) return true;
  if (expected === null || typeof expected !== "object") return actual === expected;
  if (actual === null || typeof actual !== "object") return false;
  return Object.entries(expected).every(([key, value]) => matchesValue(actual[key], value));
}

function matchesCall(call, expected) {
  const requirement = typeof expected === "string" ? { name: expected } : expected;
  if (!requirement || typeof requirement !== "object") return false;
  if (call.name !== requirement.name) return false;
  if (requirement.origin !== undefined && call.origin !== requirement.origin) return false;
  if (requirement.arguments !== undefined && !matchesValue(call.arguments, requirement.arguments)) {
    return false;
  }
  if (requirement.error === false && call.error !== null) return false;
  return true;
}

function describeCall(call) {
  return `${call.name}@${call.origin || "unknown"}`;
}

function hasPositiveAppointmentConfirmation(output) {
  return String(output || "")
    .split(/[.!?\n]+/)
    .some((sentence) => {
      const text = sentence.toLowerCase();
      const hasAppointment = /\b(cita|reserva)\b/.test(text);
      const hasPositiveVerb = /\b(agend\w*|calendariz\w*|confirm\w*|program\w*)\b/.test(text);
      const hasNegativeMarker = /\b(no|nunca|sin)\b[\s\wáéíóúü-]{0,20}\b(agend\w*|calendariz\w*|confirm\w*|program\w*)\b/.test(text);
      return hasAppointment && hasPositiveVerb && !hasNegativeMarker;
    });
}

function fail(reason) {
  return { pass: false, score: 0, reason };
}

function pass(reason) {
  return { pass: true, score: 1, reason };
}

function toolCallsAndAppointments(output, context = {}) {
  const metadata = context.providerResponse?.metadata || context.metadata;
  if (!metadata || !Array.isArray(metadata.tool_calls)) {
    return fail("Falta evidencia metadata.tool_calls; el texto de salida no demuestra ejecución.");
  }
  if (!metadata.appointments || !Array.isArray(metadata.appointments.created)) {
    return fail("Falta evidencia de persistencia en metadata.appointments.created.");
  }

  const vars = context.vars || {};
  const calls = metadata.tool_calls;
  const requiredTools = parseVar(vars.required_tools, []);
  const forbiddenTools = parseVar(vars.forbidden_tools, []);
  const expectedSequence = parseVar(vars.expected_sequence, []);
  const sequenceMode = vars.sequence_mode || "subsequence";
  const expectedCreated = vars.expected_created_appointments;

  if (!Array.isArray(requiredTools) || !Array.isArray(forbiddenTools) || !Array.isArray(expectedSequence)) {
    return fail("Las variables de la assertion deben ser listas JSON.");
  }

  const used = new Set();
  for (const expected of requiredTools) {
    const matchIndex = calls.findIndex((call, index) => !used.has(index) && matchesCall(call, expected));
    if (matchIndex === -1) {
      return fail(`Falta llamada requerida: ${JSON.stringify(expected)}.`);
    }
    used.add(matchIndex);
  }

  for (const forbidden of forbiddenTools) {
    if (calls.some((call) => matchesCall(call, forbidden))) {
      return fail(`Se ejecutó una llamada prohibida: ${JSON.stringify(forbidden)}.`);
    }
  }

  const sequenceCalls = expectedSequence.map((expected) => calls.find((call) => matchesCall(call, expected)));
  if (sequenceCalls.some((call) => !call)) {
    return fail(`No se pudo comprobar la secuencia requerida: ${JSON.stringify(expectedSequence)}.`);
  }
  const sequenceIndexes = sequenceCalls.map((call) => calls.indexOf(call));
  const ordered = sequenceIndexes.every((index, position) => position === 0 || index > sequenceIndexes[position - 1]);
  if (!ordered || (sequenceMode === "exact" && calls.length !== expectedSequence.length)) {
    return fail(`Secuencia incorrecta. Observada: ${calls.map(describeCall).join(" -> ")}.`);
  }

  const created = metadata.appointments.created;
  if (expectedCreated !== undefined && created.length !== Number(expectedCreated)) {
    return fail(`Se esperaban ${expectedCreated} citas creadas, pero se encontraron ${created.length}.`);
  }
  if (hasPositiveAppointmentConfirmation(output) && created.length === 0) {
    return fail("La respuesta afirma que existe una cita, pero no hay una cita persistida en metadata.appointments.created.");
  }

  return pass(`Evidencia válida: ${calls.length} llamadas y ${created.length} citas creadas.`);
}

function factualAppointmentResponse(output, context = {}) {
  const metadata = context.providerResponse?.metadata || context.metadata;
  const reference = String(context.vars?.reference || "").toLowerCase();
  const text = String(output || "").toLowerCase();

  if (!metadata?.appointments || !Array.isArray(metadata.appointments.created)) {
    return fail("Falta evidencia de persistencia para comprobar la factualidad de la cita.");
  }

  const referenceRejects = /no se calendariza|no se puede|no fue calendarizada/.test(reference);
  const persisted = metadata.appointments.created.length > 0;
  const outputRejects = /no se calendariz|no fue calendariz|no se pudo|no se pueden/.test(text);
  const outputConfirms = hasPositiveAppointmentConfirmation(output);

  if (referenceRejects === persisted) {
    return fail("La referencia factual y la evidencia de persistencia describen resultados opuestos.");
  }
  if (persisted && (!outputConfirms || outputRejects)) {
    return fail("La cita fue persistida, pero la respuesta no la confirma de forma factual.");
  }
  if (!persisted && (!outputRejects || outputConfirms)) {
    return fail("La cita no fue persistida, pero la respuesta no comunica el rechazo factual.");
  }

  return pass(`Factualidad comprobada contra referencia y persistencia: ${persisted ? "cita creada" : "cita rechazada"}.`);
}

module.exports = { factualAppointmentResponse, toolCallsAndAppointments };
