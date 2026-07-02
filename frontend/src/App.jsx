import React, { useEffect, useMemo, useRef, useState } from "react";
import * as api from "./api.js";

// Erlaubt: leer, "-", oder Note 1..6 (Komma oder Punkt, eine Nachkommastelle).
function isValidGrade(v) {
  const s = (v || "").trim();
  if (s === "" || s === "-") return true;
  if (!/^[1-6]([.,]\d)?$/.test(s)) return false;
  const f = parseFloat(s.replace(",", "."));
  return f >= 1 && f <= 6;
}

function Login({ onLogin }) {
  const [kuerzel, setKuerzel] = useState("");
  const [passwort, setPasswort] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const r = await api.login(kuerzel, passwort);
      localStorage.setItem("token", r.token);
      onLogin(r.kuerzel);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card login" onSubmit={submit}>
      <h1>Notensammler</h1>
      <label>
        Lehrerkürzel
        <input
          value={kuerzel}
          onChange={(e) => setKuerzel(e.target.value)}
          autoFocus
          autoComplete="username"
        />
      </label>
      <label>
        Passwort
        <input
          type="password"
          value={passwort}
          onChange={(e) => setPasswort(e.target.value)}
          autoComplete="current-password"
        />
      </label>
      {error && <p className="error" role="alert">{error}</p>}
      <button disabled={busy || !kuerzel || !passwort}>
        {busy ? "Anmelden…" : "Anmelden"}
      </button>
    </form>
  );
}

// Gewicht: leer oder Zahl >= 0.
function isValidWeight(v) {
  const s = (v || "").trim();
  if (s === "") return true;
  const f = parseFloat(s.replace(",", "."));
  return !isNaN(f) && f >= 0;
}

function GradeGrid({ cls, onBack }) {
  const [data, setData] = useState(null);
  const [values, setValues] = useState({});   // Noten "row:col" -> Wert
  const [meta, setMeta] = useState({});        // Kopfzeilen "row:col" -> Wert
  const [names, setNames] = useState({});      // Name/Vorname "row:col" -> Wert
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [allColumns, setAllColumns] = useState(false);
  const [exporting, setExporting] = useState(false);

  function apply(d) {
    setData(d);
    const initV = {};
    for (const st of d.students) {
      for (const c of d.columns) {
        if (!c.editable) continue; // Schnitt-Spalten sind nur Anzeige
        initV[`${st.row}:${c.col}`] = d.grades[st.row]?.[c.col] ?? "";
      }
    }
    setValues(initV);
    const initM = {};
    for (const mr of d.meta_rows || []) {
      // Kopfzeilen gelten nur für Fach-(grade-)Spalten, nicht für Schnitt/Endnote.
      for (const c of d.columns) {
        if (c.role !== "grade") continue;
        initM[`${mr.row}:${c.col}`] = d.meta?.[mr.row]?.[c.col] ?? "";
      }
    }
    setMeta(initM);
    const initN = {};
    if (d.can_edit_meta) {
      for (const st of d.students) {
        initN[`${st.row}:B`] = st.name ?? "";
        initN[`${st.row}:C`] = st.vorname ?? "";
      }
    }
    setNames(initN);
  }

  useEffect(() => {
    let alive = true;
    setError("");
    api
      .getStudents(cls, allColumns)
      .then((d) => alive && apply(d))
      .catch((e) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [cls, allColumns]);

  async function doExport() {
    setError("");
    setExporting(true);
    try {
      const blob = await api.exportClass(cls, allColumns);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${cls}.ods`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e.message);
    } finally {
      setExporting(false);
    }
  }

  const invalid = useMemo(
    () => Object.entries(values).filter(([, v]) => !isValidGrade(v)).map(([k]) => k),
    [values]
  );
  const metaInvalid = useMemo(() => {
    if (!data) return [];
    const weightRow = (data.meta_rows || []).find((m) => m.kind === "number")?.row;
    return Object.entries(meta)
      .filter(([k, v]) => Number(k.split(":")[0]) === weightRow && !isValidWeight(v))
      .map(([k]) => k);
  }, [meta, data]);

  const hasErrors = invalid.length + metaInvalid.length > 0;

  // --- Tastatur-Navigation (TAB = eine Zeile tiefer) & Spalten-Paste ---
  const editableCols = useMemo(
    () => (data?.columns || []).filter((c) => c.editable),
    [data]
  );
  const colNavIndex = useMemo(() => {
    const m = {};
    editableCols.forEach((c, i) => (m[c.col] = i));
    return m;
  }, [editableCols]);
  const cellRefs = useRef({});

  function focusCell(ci, si) {
    const el = cellRefs.current[`${ci}:${si}`];
    if (el) {
      el.focus();
      el.select?.();
    }
  }

  function onCellKeyDown(e, ci, si) {
    if (e.key !== "Tab") return;
    const nStud = data.students.length;
    const nCol = editableCols.length;
    if (e.shiftKey) {
      if (si > 0) {
        e.preventDefault();
        focusCell(ci, si - 1);
      } else if (ci > 0) {
        e.preventDefault();
        focusCell(ci - 1, nStud - 1);
      }
      // sonst: Standardverhalten (Fokus verlässt das Raster)
    } else {
      if (si < nStud - 1) {
        e.preventDefault();
        focusCell(ci, si + 1);
      } else if (ci < nCol - 1) {
        e.preventDefault();
        focusCell(ci + 1, 0);
      }
    }
  }

  // Kopierte Spalte einfügen: mehrere (durch Whitespace getrennte) Werte
  // werden ab der aktuellen Zeile nach unten verteilt.
  function onCellPaste(e, ci, si) {
    const text = (e.clipboardData || window.clipboardData).getData("text");
    let tokens;
    if (/[\r\n]/.test(text)) {
      // Spaltenkopie aus Tabellenkalkulation: zeilenweise trennen und
      // Leerzeilen als leere Werte BEHALTEN, damit die Zeilen ausgerichtet bleiben.
      tokens = text.replace(/\r\n?/g, "\n").split("\n").map((t) => t.trim());
      while (tokens.length && tokens[tokens.length - 1] === "") tokens.pop();
    } else {
      // Einzelne Zeile: durch Leerzeichen getrennte Werte.
      tokens = text.split(/\s+/).filter(Boolean);
    }
    if (tokens.length <= 1) return; // ein Wert -> normales Einfügen
    e.preventDefault();
    const col = editableCols[ci].col;
    setValues((prev) => {
      const next = { ...prev };
      for (let k = 0; k < tokens.length && si + k < data.students.length; k++) {
        const row = data.students[si + k].row;
        next[`${row}:${col}`] = tokens[k];
      }
      return next;
    });
    setMsg("");
  }

  // Kopierte Namensspalte(n) einfügen: eine Spalte (nur Name/Vorname) wird nach
  // unten verteilt; zwei tab-getrennte Spalten füllen Name UND Vorname.
  function onNamePaste(e, si, anchorCol) {
    const text = (e.clipboardData || window.clipboardData).getData("text");
    if (!/[\r\n\t]/.test(text)) return; // ein einzelner Wert -> normal
    e.preventDefault();
    const rows = text.replace(/\r\n?/g, "\n").split("\n");
    while (rows.length && rows[rows.length - 1] === "") rows.pop();
    const twoCols = rows.some((r) => r.includes("\t"));
    setNames((prev) => {
      const next = { ...prev };
      for (let k = 0; k < rows.length && si + k < data.students.length; k++) {
        const row = data.students[si + k].row;
        if (twoCols) {
          const cells = rows[k].split("\t");
          next[`${row}:B`] = (cells[0] ?? "").trim();
          next[`${row}:C`] = (cells[1] ?? "").trim();
        } else {
          next[`${row}:${anchorCol}`] = rows[k].trim();
        }
      }
      return next;
    });
    setMsg("");
  }

  function setCell(row, col, v) {
    setValues((prev) => ({ ...prev, [`${row}:${col}`]: v }));
    setMsg("");
  }
  function setMetaCell(row, col, v) {
    setMeta((prev) => ({ ...prev, [`${row}:${col}`]: v }));
    setMsg("");
  }
  function setNameCell(row, col, v) {
    setNames((prev) => ({ ...prev, [`${row}:${col}`]: v }));
    setMsg("");
  }

  async function save() {
    setError("");
    setMsg("");
    if (hasErrors) {
      setError("Bitte zuerst ungültige Eingaben korrigieren.");
      return;
    }
    const toEntries = (obj) =>
      Object.entries(obj).map(([k, v]) => {
        const [row, col] = k.split(":");
        return { row: Number(row), col, value: v };
      });
    const entries = [
      ...toEntries(values),
      ...toEntries(meta),
      ...toEntries(names),
    ];
    setBusy(true);
    try {
      const r = await api.submitGrades(cls, entries);
      // Neu laden, damit z. B. geänderte Kürzel im Spaltenkopf erscheinen.
      const fresh = await api.getStudents(cls, allColumns);
      apply(fresh);
      setMsg(`Gespeichert (${r.written} Einträge).`);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (error && !data) return <ErrorBox msg={error} onBack={onBack} />;
  if (!data) return <p className="card">Lade Klasse {cls}…</p>;

  return (
    <div className="card grid-card">
      <div className="toolbar">
        <button className="link" onClick={onBack}>&larr; Klassen</button>
        <h2>Klasse {data.class}</h2>
        {data.can_edit_meta && (
          <div className="ct-tools">
            <label className="switch">
              <input
                type="checkbox"
                checked={allColumns}
                onChange={(e) => setAllColumns(e.target.checked)}
              />
              Alle Spalten und Zeilen anzeigen
            </label>
            <button onClick={doExport} disabled={exporting}>
              {exporting ? "Exportiere…" : "Noten exportieren (.ods)"}
            </button>
          </div>
        )}
      </div>
      <p className="tip">
        Tipp: <kbd>Tab</kbd> springt eine Zeile tiefer. Eine kopierte Spalte
        (mehrere Werte) kann in eine Zelle eingefügt werden – die Werte werden
        automatisch nach unten verteilt.
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th className="sticky">Nr</th>
              <th className="sticky name">Name, Vorname</th>
              {data.columns.map((c) => (
                <th
                  key={c.col}
                  className={`role-${c.role}`}
                  title={
                    c.owner
                      ? `${c.description} · Spalte ${c.col} · Lehrer ${c.owner}`
                      : `${c.description} · Spalte ${c.col}`
                  }
                >
                  <span className="kuerzel">{c.owner || " "}</span>
                  {c.block && <span className="block">{c.block}</span>}
                  <span className="fach">{c.label}</span>
                  <span className="sub">Spalte {c.col}</span>
                </th>
              ))}
            </tr>
          </thead>
          {data.can_edit_meta && (
            <tbody className="meta-body">
              {data.meta_rows.map((mr) => (
                <tr key={mr.row}>
                  <td className="sticky" />
                  <td className="sticky name meta-label">{mr.label}</td>
                  {data.columns.map((c) => {
                    if (c.role !== "grade") return <td key={c.col} />;
                    const key = `${mr.row}:${c.col}`;
                    const isNum = mr.kind === "number";
                    const bad = isNum && !isValidWeight(meta[key]);
                    const cls = bad
                      ? "grade bad"
                      : isNum
                      ? "grade meta-input"
                      : "meta-input meta-text";
                    return (
                      <td key={c.col}>
                        <input
                          className={cls}
                          inputMode={isNum ? "decimal" : "text"}
                          value={meta[key] ?? ""}
                          aria-label={`${mr.label} für Spalte ${c.col}`}
                          aria-invalid={bad}
                          onChange={(e) => setMetaCell(mr.row, c.col, e.target.value)}
                        />
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          )}
          <tbody>
            {data.students.map((st, si) => (
              <tr key={st.row}>
                <td className="sticky">{st.nr}</td>
                {data.can_edit_meta ? (
                  <td className="sticky name name-edit">
                    <input
                      className="name-input"
                      value={names[`${st.row}:B`] ?? ""}
                      placeholder="Name"
                      aria-label={`Name Zeile ${st.row}`}
                      onChange={(e) => setNameCell(st.row, "B", e.target.value)}
                      onPaste={(e) => onNamePaste(e, si, "B")}
                    />
                    <input
                      className="name-input"
                      value={names[`${st.row}:C`] ?? ""}
                      placeholder="Vorname"
                      aria-label={`Vorname Zeile ${st.row}`}
                      onChange={(e) => setNameCell(st.row, "C", e.target.value)}
                      onPaste={(e) => onNamePaste(e, si, "C")}
                    />
                  </td>
                ) : (
                  <td className="sticky name">
                    {[st.name, st.vorname].filter(Boolean).join(", ") || (
                      <em>— Zeile {st.row} —</em>
                    )}
                  </td>
                )}
                {data.columns.map((c) => {
                  if (!c.editable) {
                    // Schnitt: nur Anzeige (berechneter Wert / Formel)
                    return (
                      <td key={c.col} className="readonly">
                        {data.grades[st.row]?.[c.col] ?? ""}
                      </td>
                    );
                  }
                  const key = `${st.row}:${c.col}`;
                  const bad = !isValidGrade(values[key]);
                  const ci = colNavIndex[c.col];
                  return (
                    <td key={c.col}>
                      <input
                        ref={(el) => (cellRefs.current[`${ci}:${si}`] = el)}
                        className={`grade role-${c.role}${bad ? " bad" : ""}`}
                        inputMode="decimal"
                        value={values[key] ?? ""}
                        aria-label={`${c.description} für ${st.name || "Zeile " + st.row}`}
                        aria-invalid={bad}
                        onChange={(e) => setCell(st.row, c.col, e.target.value)}
                        onKeyDown={(e) => onCellKeyDown(e, ci, si)}
                        onPaste={(e) => onCellPaste(e, ci, si)}
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
          {data.footer && (
            <tfoot>
              <tr>
                <td className="sticky" />
                <td className="sticky name footer-label">
                  {data.footer_label || "Durchschnitt"}
                </td>
                {data.columns.map((c) => (
                  <td key={c.col} className="footer-cell">
                    {data.footer[c.col] ?? ""}
                  </td>
                ))}
              </tr>
            </tfoot>
          )}
        </table>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {msg && <p className="ok" role="status">{msg}</p>}
      <div className="actions">
        <button onClick={save} disabled={busy || hasErrors}>
          {busy ? "Speichere…" : "Speichern"}
        </button>
        {hasErrors && (
          <span className="hint">
            {invalid.length + metaInvalid.length} ungültige Eingabe(n)
          </span>
        )}
      </div>
    </div>
  );
}

function ClassList({ onPick }) {
  const [classes, setClasses] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api.getClasses().then((d) => setClasses(d.classes)).catch((e) => setError(e.message));
  }, []);
  if (error) return <ErrorBox msg={error} />;
  if (!classes) return <p className="card">Lade Klassen…</p>;
  if (classes.length === 0)
    return <p className="card">Keine Klassen mit Bearbeitungsrechten.</p>;
  return (
    <div className="card">
      <h2>Klasse wählen</h2>
      <ul className="classlist">
        {classes.map((c) => (
          <li key={c.class}>
            <button onClick={() => onPick(c.class)}>
              <strong>{c.class}</strong>
              <span>
                {c.is_classteacher ? "Klassenlehrer · " : ""}
                {c.editable_count} Spalte(n)
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ErrorBox({ msg, onBack }) {
  return (
    <div className="card">
      <p className="error" role="alert">{msg}</p>
      {onBack && <button className="link" onClick={onBack}>Zurück</button>}
    </div>
  );
}

export default function App() {
  const [teacher, setTeacher] = useState(null);
  const [cls, setCls] = useState(null);

  function logout() {
    localStorage.removeItem("token");
    setTeacher(null);
    setCls(null);
  }

  if (!teacher) return <div className="wrap"><Login onLogin={setTeacher} /></div>;

  return (
    <div className="wrap">
      <header className="topbar">
        <span>Angemeldet als <strong>{teacher}</strong></span>
        <button className="link" onClick={logout}>Abmelden</button>
      </header>
      {cls ? (
        <GradeGrid cls={cls} onBack={() => setCls(null)} />
      ) : (
        <ClassList onPick={setCls} />
      )}
    </div>
  );
}
