/*
 * Animaciones de la pantalla principal (GSAP). Todo es corto y sutil: se usa
 * a diario. Si Windows tiene "reducir movimiento", se muestra el estado final
 * sin animar. Si GSAP no carga, la app funciona igual (todas las funciones
 * salen temprano).
 *
 *  - progreso: pasos de la validacion con brillo que barre ("Light Sweep").
 *  - resultados: contadores que suben, tarjetas escalonadas, celebracion de
 *    particulas en los dias que cuadran, temblor leve en las diferencias.
 *  - comite: la pregunta del alquiler entra con revelado de mascara.
 */
window.Animaciones = (function () {
  // Azar para posiciones de particulas. No es seguridad, pero se usa
  // crypto.getRandomValues para no depender de Math.random (SonarCloud S2245).
  const _buf = new Uint32Array(1);
  const azar = () => crypto.getRandomValues(_buf)[0] / 4294967296;
  const hayGsap = typeof gsap !== "undefined";
  const reducido = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const animar = hayGsap && !reducido;

  // ---- 2. Progreso de la validacion --------------------------------------
  // El servidor responde todo junto al final; los pasos avanzan con tiempos
  // aproximados (medidos con datos reales: ~2-3 s OpenCorp, ~5 s Excel) y el
  // ultimo queda activo hasta que llega la respuesta.
  const PASOS = [
    { texto: "Conectando con OpenCorp", ms: 0 },
    { texto: "Leyendo Caja 3", ms: 2500 },
    { texto: "Leyendo CONTABILIDAD", ms: 5000 },
    { texto: "Cruzando JP", ms: 7500 },
    { texto: "Cruzando RC", ms: 9500 },
  ];
  let timers = [];

  function pintarPasos(activo, terminado) {
    const cont = document.getElementById("progreso");
    cont.innerHTML = PASOS.map((p, i) => {
      const hecho = terminado || i < activo;
      const actual = !terminado && i === activo;
      let clase = "paso-espera", icono = "radio_button_unchecked";
      if (hecho) { clase = "paso-hecho"; icono = "check_circle"; }
      else if (actual) { clase = "paso-activo"; icono = "progress_activity"; }
      return `${i ? '<span class="paso-flecha material-symbols-outlined text-[14px]">chevron_right</span>' : ""}
        <span class="paso ${clase}"><span class="material-symbols-outlined text-[15px] ${actual ? "girando" : ""}">${icono}</span>${p.texto}</span>`;
    }).join("") + (terminado ? '<span class="paso-flecha material-symbols-outlined text-[14px]">chevron_right</span><span class="paso paso-listo"><span class="material-symbols-outlined text-[15px]">task_alt</span>Listo</span>' : "");
  }

  function progresoIniciar() {
    const cont = document.getElementById("progreso");
    timers.forEach(clearTimeout); timers = [];
    cont.classList.remove("hidden");
    pintarPasos(0, false);
    if (animar) gsap.from(cont, { opacity: 0, y: -8, duration: 0.3, ease: "power2.out" });
    PASOS.forEach((p, i) => { if (i) timers.push(setTimeout(() => pintarPasos(i, false), p.ms)); });
  }

  function progresoTerminar(ok) {
    const cont = document.getElementById("progreso");
    timers.forEach(clearTimeout); timers = [];
    if (!ok) { cont.classList.add("hidden"); return; }
    pintarPasos(PASOS.length, true);
    if (!animar) { setTimeout(() => cont.classList.add("hidden"), 800); return; }
    gsap.from(cont.querySelectorAll(".paso-hecho, .paso-listo"), { scale: 0.9, duration: 0.3, stagger: 0.04, ease: "back.out(3)" });
    gsap.to(cont, { opacity: 0, y: -6, duration: 0.4, delay: 1.1, ease: "power2.in",
      onComplete: () => { cont.classList.add("hidden"); gsap.set(cont, { clearProps: "all" }); } });
  }

  // ---- 3. Resultados ------------------------------------------------------
  function contar(el, hasta) {
    if (!animar) { el.textContent = hasta.toLocaleString("es-CO"); return; }
    const obj = { v: 0 };
    gsap.to(obj, { v: hasta, duration: 1.1, ease: "power2.out",
      onUpdate: () => { el.textContent = Math.round(obj.v).toLocaleString("es-CO"); } });
  }

  function resumen(dias) {
    let celdas = 0, difs = 0, cuadran = 0, total = 0;
    dias.forEach(d => ["JP", "RC"].forEach(h => {
      const x = d.hojas[h];
      if (x.fila === null || x.nueva) return;
      total += 1;
      celdas += Object.keys(x.esperado).length;
      difs += x.diferencias.length;
      if (!x.diferencias.length) cuadran += 1;
    }));
    return { celdas, difs, cuadran, total };
  }

  function celebrar(tarjeta) {
    // Pequena explosion de particulas verdes desde el centro de la tarjeta.
    const r = tarjeta.getBoundingClientRect();
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    const colores = ["#10b981", "#34d399", "#6ee7b7", "#0ea5e9", "#a7f3d0"];
    for (let i = 0; i < 18; i++) {
      const p = document.createElement("span");
      p.className = "confeti";
      p.style.background = colores[i % colores.length];
      p.style.left = cx + "px"; p.style.top = cy + "px";
      document.body.appendChild(p);
      const ang = azar() * Math.PI * 2, dist = 40 + azar() * 70;
      gsap.to(p, {
        x: Math.cos(ang) * dist, y: Math.sin(ang) * dist - 20, rotation: azar() * 360,
        opacity: 0, scale: 0.4 + azar() * 0.6, duration: 0.9 + azar() * 0.4, ease: "power2.out",
        onComplete: () => p.remove(),
      });
    }
  }

  function resultados(dias, primera) {
    const r = resumen(dias);
    const caja = document.getElementById("resumen");
    caja.classList.remove("hidden");
    contar(document.getElementById("cnt-celdas"), r.celdas);
    contar(document.getElementById("cnt-difs"), r.difs);
    contar(document.getElementById("cnt-cuadran"), r.cuadran);
    document.getElementById("cnt-total").textContent = r.total;
    if (!animar) return;

    const tarjetas = document.querySelectorAll(".dia-card");
    if (primera) {
      gsap.from(caja, { opacity: 0, y: 12, duration: 0.4, ease: "power3.out" });
      gsap.from(tarjetas, { opacity: 0, y: 24, duration: 0.5, ease: "power3.out", stagger: 0.07, delay: 0.1 });
    }
    // Celebracion solo en lo visible al inicio (maximo 6), para no saturar.
    const ok = Array.from(document.querySelectorAll(".tarjeta-ok"))
      .filter(t => t.getBoundingClientRect().top < window.innerHeight).slice(0, 6);
    ok.forEach((t, i) => gsap.delayedCall(0.5 + i * 0.12, () => {
      gsap.fromTo(t, { scale: 0.97 }, { scale: 1, duration: 0.5, ease: "elastic.out(1, 0.4)" });
      celebrar(t);
    }));
    // Temblor leve en las filas con diferencia: guia la mirada sin alarmar.
    gsap.fromTo(".fila-dif", { x: -4 }, { x: 0, duration: 0.7, ease: "elastic.out(1, 0.3)", stagger: 0.015, delay: primera ? 0.5 : 0 });
    // ---- 4. Pregunta del comite: revelado de mascara ----
    // Se anima un numero y se escribe el clip-path a mano: GSAP no interpola
    // "inset(... round 6px)" (verificado 2026-10-14: la caja quedaba oculta).
    // Al terminar se borra el clip-path, asi nunca puede quedar escondida.
    document.querySelectorAll(".pregunta-comite").forEach((el, i) => {
      const estado = { p: 0 };
      el.style.clipPath = "inset(0 100% 0 0 round 6px)";
      gsap.to(estado, {
        p: 100, duration: 0.8, ease: "power4.inOut", delay: (primera ? 0.6 : 0) + i * 0.1,
        onUpdate: () => { el.style.clipPath = `inset(0 ${100 - estado.p}% 0 0 round 6px)`; },
        onComplete: () => {
          el.style.clipPath = "";
          gsap.fromTo(el.querySelector(".alquiler-comite"),
            { boxShadow: "0 0 0 0 rgba(99,102,241,0.6)" },
            { boxShadow: "0 0 0 8px rgba(99,102,241,0)", duration: 0.9, repeat: 1, ease: "power2.out" });
        },
      });
    });
  }

  return { progresoIniciar, progresoTerminar, resultados };
})();
