// Dünner Wrapper um die REST-API des Backends.
const BASE = "/api";

function authHeader() {
  const t = localStorage.getItem("token");
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function handle(res) {
  if (!res.ok) {
    let msg = `Fehler ${res.status}`;
    try {
      const j = await res.json();
      if (j.detail) msg = j.detail;
    } catch (e) {
      /* ignore */
    }
    throw new Error(msg);
  }
  return res.json();
}

export async function login(kuerzel, passwort) {
  const res = await fetch(`${BASE}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kuerzel, passwort }),
  });
  return handle(res);
}

export async function getClasses() {
  return handle(await fetch(`${BASE}/classes`, { headers: authHeader() }));
}

export async function getStudents(cls, allColumns = false) {
  const q = allColumns ? "?all_columns=1" : "";
  return handle(
    await fetch(`${BASE}/classes/${encodeURIComponent(cls)}/students${q}`, {
      headers: authHeader(),
    })
  );
}

export async function exportClass(cls) {
  const res = await fetch(
    `${BASE}/classes/${encodeURIComponent(cls)}/export`,
    { headers: authHeader() }
  );
  if (!res.ok) {
    let msg = `Fehler ${res.status}`;
    try {
      const j = await res.json();
      if (j.detail) msg = j.detail;
    } catch (e) {
      /* ignore */
    }
    throw new Error(msg);
  }
  return res.blob();
}

export async function submitGrades(cls, entries) {
  const res = await fetch(
    `${BASE}/classes/${encodeURIComponent(cls)}/grades`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeader() },
      body: JSON.stringify({ entries }),
    }
  );
  return handle(res);
}
