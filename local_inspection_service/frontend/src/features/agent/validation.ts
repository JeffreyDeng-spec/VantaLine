import type { Schema } from "./contracts";

export function validate(schema: Schema, value: unknown, path = "input", depth = 0): void {
  if (depth > 24) throw new Error(`${path}: nesting limit exceeded`);
  if (schema.anyOf) {
    for (const option of schema.anyOf) {
      try { validate(option, value, path, depth + 1); return; } catch { /* try next declared alternative */ }
    }
    throw new Error(`${path}: does not match an allowed input type`);
  }
  if (schema.enum && !schema.enum.some(item => JSON.stringify(item) === JSON.stringify(value))) throw new Error(`${path}: invalid choice`);
  if (schema.type === "null" && value !== null) throw new Error(`${path}: expected null`);
  if (schema.type === "string") {
    if (typeof value !== "string" || value.length > (schema.maxLength ?? 8192) || value.length < (schema.minLength ?? 0)) throw new Error(`${path}: invalid string`);
  }
  if (schema.type === "number" || schema.type === "integer") {
    if (typeof value !== "number" || !Number.isFinite(value) || (schema.type === "integer" && !Number.isInteger(value)) || value < (schema.minimum ?? -Infinity) || value > (schema.maximum ?? Infinity)) throw new Error(`${path}: invalid number`);
  }
  if (schema.type === "boolean" && typeof value !== "boolean") throw new Error(`${path}: expected boolean`);
  if (schema.type === "array") {
    if (!Array.isArray(value) || value.length > (schema.maxItems ?? 500) || value.length < (schema.minItems ?? 0)) throw new Error(`${path}: invalid array`);
    value.forEach((item, index) => validate(schema.items ?? {}, item, `${path}[${index}]`, depth + 1));
  }
  if (schema.type === "object") {
    if (!value || typeof value !== "object" || Array.isArray(value) || Object.getPrototypeOf(value) !== Object.prototype) throw new Error(`${path}: expected plain object`);
    const input = value as Record<string, unknown>;
    for (const key of schema.required ?? []) if (!(key in input) || input[key] === undefined) throw new Error(`${path}.${key}: required`);
    for (const [key, item] of Object.entries(input)) {
      if (["__proto__", "prototype", "constructor"].includes(key)) throw new Error(`${path}: unsafe property`);
      const child = schema.properties?.[key];
      if (child) validate(child, item, `${path}.${key}`, depth + 1);
      else if (schema.additionalProperties === false) throw new Error(`${path}.${key}: unknown field`);
      else if (typeof schema.additionalProperties === "object") validate(schema.additionalProperties, item, `${path}.${key}`, depth + 1);
    }
  }
}

const privateKey = /(^|_)(password|secret|token|authorization|cookie|api_key|image_api_key|attempt_token|session_id|raw_json|provider_config)(_|$)/i;
export function safeResult(value: unknown, depth = 0): unknown {
  if (depth > 16) return "[depth limit]";
  if (value === null || typeof value === "boolean" || typeof value === "number") return value;
  if (typeof value === "string") {
    if (/^(data:|Bearer\s)/i.test(value)) return "[private payload omitted]";
    if (/^(\/Users\/|\/home\/|\/opt\/|\/srv\/|\/private\/|\/tmp\/|\/var\/|[A-Z]:\\)/.test(value)) return "[server path omitted]";
    return value.length > 8192 ? `${value.slice(0, 8192)}…` : value;
  }
  if (Array.isArray(value)) return value.map(item => safeResult(item, depth + 1));
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).filter(([key]) => {
    const normalized=key.replace(/([a-z0-9])([A-Z])/g, "$1_$2");
    return !privateKey.test(normalized) && !/_(path|dir)$/i.test(normalized);
  }).map(([key, item]) => [key, safeResult(item, depth + 1)]));
  return null;
}
