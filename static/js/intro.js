/*
 * Intro del login: cifras sueltas (montos, rutas) que flotan y se arman en
 * el logo "VK" -- el desorden de la contabilidad que se ordena -- y luego
 * se dispersan como fondo. Inspirado en "Particle Scatter & Assemble" y
 * "Kinetic Type Sweep" de awesome-ai-motion.
 *
 * Solo corre una vez por ventana (sessionStorage), se salta con clic/tecla
 * y respeta "reducir movimiento" de Windows.
 */
(function () {
  // Azar para posiciones de particulas. No es seguridad, pero se usa
  // crypto.getRandomValues para no depender de Math.random (SonarCloud S2245).
  const _buf = new Uint32Array(1);
  const azar = () => crypto.getRandomValues(_buf)[0] / 4294967296;
  const canvas = document.getElementById("intro-canvas");
  const contenido = document.getElementById("login-contenido");
  const saludo = document.getElementById("saludo");
  if (!canvas || !contenido || typeof gsap === "undefined") return;

  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  let ancho = 0, alto = 0;
  function medir() {
    ancho = window.innerWidth; alto = window.innerHeight;
    canvas.width = ancho * dpr; canvas.height = alto * dpr;
    canvas.style.width = ancho + "px"; canvas.style.height = alto + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  medir();
  window.addEventListener("resize", medir);

  // Saludo segun la hora
  const h = new Date().getHours();
  const texto = (h < 12 ? "Buenos días" : h < 19 ? "Buenas tardes" : "Buenas noches") + ", Karina";
  saludo.innerHTML = texto.split("").map(c =>
    `<span class="inline-block will-change-transform">${c === " " ? "&nbsp;" : c}</span>`).join("");
  const letras = saludo.querySelectorAll("span");

  const reducido = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let yaVista = false;
  try { yaVista = sessionStorage.getItem("intro-vista") === "1"; } catch (e) { /* sin storage: se muestra */ }

  // ---- Particulas -------------------------------------------------------
  const GLIFOS = ["0","1","2","3","4","5","6","7","8","9","$",".",",","JP","RC","%"];
  const COLORES = ["#4338ca", "#6366f1", "#0ea5e9", "#10b981", "#94a3b8"];
  const TAMANOS = [10, 12, 14];

  function puntosDelLogo() {
    // Dibuja "VK" en un canvas oculto y toma una muestra de sus pixeles.
    const off = document.createElement("canvas");
    const w = 420, hh = 220;
    off.width = w; off.height = hh;
    const o = off.getContext("2d");
    o.fillStyle = "#000";
    o.font = "800 200px Inter, 'Segoe UI', sans-serif";
    o.textAlign = "center"; o.textBaseline = "middle";
    o.fillText("VK", w / 2, hh / 2 + 8);
    const datos = o.getImageData(0, 0, w, hh).data;
    const pts = [];
    const paso = ancho < 700 ? 8 : 5;
    for (let y = 0; y < hh; y += paso) {
      for (let x = 0; x < w; x += paso) {
        if (datos[(y * w + x) * 4 + 3] > 140) pts.push({ x: x - w / 2, y: y - hh / 2 });
      }
    }
    return pts;
  }

  const objetivo = puntosDelLogo();
  const escala = Math.min(1.5, ancho / 640);
  const cx = ancho / 2, cy = alto * 0.42;
  const particulas = objetivo.map(p => ({
    x: azar() * ancho,
    y: azar() * alto,
    tx: cx + p.x * escala,
    ty: cy + p.y * escala,
    alfa: 0,
    tam: TAMANOS[(azar() * TAMANOS.length) | 0],
    rot: (azar() - 0.5) * 2,
    glifo: GLIFOS[(azar() * GLIFOS.length) | 0],
    color: COLORES[(azar() * COLORES.length) | 0],
    deriva: { x: (azar() - 0.5) * 0.25, y: (azar() - 0.5) * 0.25 },
  }));

  let flotando = false;
  // Rendimiento: la fuente se fija una vez por tamano (no por particula) y
  // la rotacion va con setTransform directo, sin save/restore.
  const porTamano = {};
  function dibujar() {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, ancho, alto);
    for (const t of TAMANOS) {
      ctx.font = `600 ${t}px 'JetBrains Mono', monospace`;
      for (const p of porTamano[t]) {
        if (flotando) {
          p.x += p.deriva.x; p.y += p.deriva.y;
          if (p.x < -20) p.x = ancho + 20; else if (p.x > ancho + 20) p.x = -20;
          if (p.y < -20) p.y = alto + 20; else if (p.y > alto + 20) p.y = -20;
        }
        if (p.alfa <= 0.01) continue;
        const c = Math.cos(p.rot) * dpr, s = Math.sin(p.rot) * dpr;
        ctx.setTransform(c, s, -s, c, p.x * dpr, p.y * dpr);
        ctx.globalAlpha = p.alfa;
        ctx.fillStyle = p.color;
        ctx.fillText(p.glifo, 0, 0);
      }
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.globalAlpha = 1;
  }
  TAMANOS.forEach(t => { porTamano[t] = particulas.filter(p => p.tam === t); });
  // Ciclo de dibujo propio (no gsap.ticker): el fondo sigue flotando aunque
  // no quede ninguna animacion de GSAP activa.
  (function ciclo() { dibujar(); requestAnimationFrame(ciclo); })();

  function estadoFinal() {
    // Fondo tenue de cifras flotando + formulario visible.
    flotando = true;
    particulas.forEach(p => { p.alfa = 0.12; p.rot = (azar() - 0.5) * 2; });
    gsap.set(contenido, { opacity: 1, y: 0 });
    gsap.set(letras, { opacity: 1, yPercent: 0 });
  }

  if (reducido || yaVista) {
    particulas.forEach(p => { p.x = azar() * ancho; p.y = azar() * alto; });
    estadoFinal();
    return;
  }

  gsap.set(contenido, { opacity: 0, y: 24 });
  gsap.set(letras, { opacity: 0, yPercent: 120 });

  const tl = gsap.timeline({
    onComplete: () => { try { sessionStorage.setItem("intro-vista", "1"); } catch (e) { /* nada */ } },
  });
  // 1. Las cifras aparecen dispersas
  tl.to(particulas, { alfa: 0.9, duration: 0.6, stagger: { amount: 0.4, from: "random" }, ease: "power1.out" });
  // 2. Se arman en "VK"
  tl.to(particulas, {
    x: i => particulas[i].tx, y: i => particulas[i].ty, rot: 0,
    duration: 1.5, ease: "expo.inOut", stagger: { amount: 0.35, from: "random" },
  }, "-=0.2");
  // 3. Pausa con el logo armado, luego se abren hacia afuera y quedan de fondo
  tl.to(particulas, {
    x: i => particulas[i].tx + (particulas[i].tx - cx) * (1.5 + azar() * 2) + (azar() - 0.5) * 200,
    y: i => particulas[i].ty + (particulas[i].ty - cy) * (1.5 + azar() * 2) + (azar() - 0.5) * 200,
    alfa: 0.12, rot: () => (azar() - 0.5) * 2,
    duration: 1.2, ease: "power3.out", stagger: { amount: 0.2, from: "center" },
    onComplete: () => { flotando = true; },
  }, "+=0.5");
  // 4. Saludo letra por letra y entra el formulario
  tl.to(letras, { opacity: 1, yPercent: 0, duration: 0.6, ease: "back.out(2)", stagger: 0.035 }, "-=1.0");
  tl.to(contenido, { opacity: 1, y: 0, duration: 0.7, ease: "power3.out" }, "-=0.5");

  // Solo para revisar la intro cuadro a cuadro (capturas): ?intro_t=2.9
  const congelar = new URLSearchParams(location.search).get("intro_t");
  if (congelar !== null) {
    tl.pause(parseFloat(congelar));
    if (tl.time() >= tl.duration()) estadoFinal();
  }

  function saltar() {
    if (!tl.isActive()) return;
    tl.progress(1);
    estadoFinal();
  }
  window.addEventListener("click", saltar, { once: true });
  window.addEventListener("keydown", saltar, { once: true });
})();
