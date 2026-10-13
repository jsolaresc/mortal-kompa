// =====================================================================
// flow.js — cómo se encadenan las pantallas (menús -> selección ->
// escenario -> pelea -> fin) para cada modo de juego, más la escena de
// pelea local (con pausa y menú de revancha).
// =====================================================================
import * as C from "./config.js";
import { COLORS } from "./config.js";
import * as UI from "./ui.js";
import { audio } from "./audio.js";
import { DB, loadCharacterFrames, randomStage, secretStage } from "./assets.js";
import { CPUInput, ok, escJustPressed } from "./input.js";
import { Stage } from "./stage.js";
import { Match } from "./match.js";
import { ListMenu, DifficultyScene, OptionsScene, TournamentSizeScene, playMenuMusic } from "./scenes/menus.js";
import { CharSelectScene, StageSelectScene } from "./scenes/select.js";
import { startTower } from "./scenes/tower.js";
import { startLocalTournament } from "./scenes/tournament.js";
import { hostOnline, joinOnlineScene, showJoinPanel } from "./scenes/online.js";

// ---------------------------------------------------------------------
// Menús
// ---------------------------------------------------------------------
export function mainMenu(app, index = 0) {
  app.setScene(new ListMenu(app, {
    showLogo: true, index,
    items: [
      { label: "1 Jugador", action: () => onePlayerMenu(app) },
      { label: "Multijugador", action: () => multiplayerMenu(app) },
      { label: "Opciones", action: () => app.setScene(new OptionsScene(app, { onBack: () => mainMenu(app, 2) })) },
    ],
  }));
}

export function onePlayerMenu(app, index = 0) {
  app.setScene(new ListMenu(app, {
    title: "1 JUGADOR", index,
    onBack: () => mainMenu(app, 0),
    items: [
      { label: "Torre de Batalla", action: () => askDifficulty(app, "DIFICULTAD INICIAL DE LA TORRE", (lvl) => startTower(app, lvl), () => onePlayerMenu(app, 0)) },
      { label: "Pelea contra CPU", action: () => askDifficulty(app, "DIFICULTAD DE LA CPU", (lvl) => startCpuFight(app, lvl), () => onePlayerMenu(app, 1)) },
      { label: "Volver", action: () => mainMenu(app, 0) },
    ],
  }));
}

export function multiplayerMenu(app, index = 0) {
  app.setScene(new ListMenu(app, {
    title: "MULTIJUGADOR", index,
    onBack: () => mainMenu(app, 1),
    items: [
      { label: "Local", action: () => localMenu(app) },
      { label: "Online", action: () => onlineMenu(app) },
      { label: "Volver", action: () => mainMenu(app, 1) },
    ],
  }));
}

// mismo equipo (teclado / joysticks / un celular)
export function localMenu(app, index = 0) {
  app.setScene(new ListMenu(app, {
    title: "LOCAL", index,
    onBack: () => multiplayerMenu(app, 0),
    items: [
      { label: "2 Jugadores", action: () => startVersusLocal(app) },
      { label: "Torneo", action: () => app.setScene(new TournamentSizeScene(app, {
        onDone: (n) => startLocalTournament(app, n), onBack: () => localMenu(app, 1),
      })) },
      { label: "Volver", action: () => multiplayerMenu(app, 0) },
    ],
  }));
}

// por internet, invitando con un link
export function onlineMenu(app, index = 0) {
  app.setScene(new ListMenu(app, {
    title: "ONLINE", index,
    onBack: () => multiplayerMenu(app, 1),
    items: [
      { label: "2 Jugadores", action: () => hostOnline(app, "versus") },
      { label: "Torneo", action: () => hostOnline(app, "tournament") },
      { label: "Unirse con un link", action: () => showJoinPanel(app, () => onlineMenu(app, 2)) },
      { label: "Volver", action: () => multiplayerMenu(app, 1) },
    ],
  }));
}

export function joinOnline(app, room) { joinOnlineScene(app, room); }

function askDifficulty(app, title, onDone, onBack) {
  app.setScene(new DifficultyScene(app, { title, onDone, onBack }));
}

// ---------------------------------------------------------------------
// Carga de una pelea (frames de los 2 luchadores + escenario)
// ---------------------------------------------------------------------
export class LoadingScene {
  constructor(app, text = "Cargando...") { this.app = app; this.text = text; }
  draw(ctx, view) {
    UI.menuBackground(ctx, view, this.app.t);
    UI.text(ctx, this.text, view.w / 2, C.BASE_H / 2, { size: 30 });
  }
}

export async function prepareFight(app, slugs, stageDef) {
  app.setScene(new LoadingScene(app));
  const [f1, f2, stage] = await Promise.all([
    loadCharacterFrames(slugs[0]), loadCharacterFrames(slugs[1]), Stage.load(stageDef),
  ]);
  return { frames: [f1, f2], stage, entries: [DB.bySlug[slugs[0]], DB.bySlug[slugs[1]]] };
}

export function playStageMusic(stage) {
  if (stage && stage.music) { audio.playMusic(stage.music, { loop: true, volume: 0.5 }); audio.musicCategory = "stage"; }
  else if (DB.menuMusic.length && !audio.isMusicPlaying()) playMenuMusic();
}

// ---------------------------------------------------------------------
// Escena de pelea local
// ---------------------------------------------------------------------
/**
 * opts: { match, pausers:[inputs], endMenu: bool, onOver(match) | onEndChoice(choice) }
 */
export class FightScene {
  constructor(app, opts) {
    this.app = app;
    this.match = opts.match;
    this.opts = opts;
    this.paused = false;
    this.pauseIndex = 0;
    this.overHandled = false;
    this.endIndex = 0;
    this.showEnd = false;
  }
  enter() { this.app.touch.fightMode = true; }
  exit() {
    this.app.touch.fightMode = false;
    audio.resumeSfx();
  }
  pauseItems() { return ["Reanudar", "Opciones", "Volver a Inicio"]; }
  endItems() { return this.opts.endItems || ["Pelear de nuevo", "Cambiar personajes", "Volver a Inicio"]; }

  update(dt) {
    const m = this.match;
    const pausers = this.opts.pausers || [this.app.inputs[0]];
    if (this.paused) {
      const inp = this.app.inputs[0];
      const items = this.pauseItems();
      if (inp.justPressed("up")) this.pauseIndex = (this.pauseIndex + items.length - 1) % items.length;
      else if (inp.justPressed("down")) this.pauseIndex = (this.pauseIndex + 1) % items.length;
      else if (ok(inp)) this.pausePick(this.pauseIndex);
      else if (inp.justPressed("cancel") || escJustPressed()) this.pausePick(0);
      // online la pelea NO se frena (los demás siguen jugando)
      if (!this.opts.net) return;
    } else if (m.phase === "fight" && (pausers.some((i) => i.justPressed("start")) || escJustPressed() || (this.opts.net && this.app.touch.pauseTapped))) {
      this.paused = true;
      this.pauseIndex = 0;
      if (!this.opts.net) { audio.pauseSfx(); audio.pauseMusic(); }
      return;
    }
    // carga del especial para el botón táctil (del luchador que maneja J1)
    const mine = m.inputs.indexOf(this.app.inputs[0]);
    this.app.touch.specialCharge = m.f[Math.max(0, mine)].hitsTakenSinceSpecial;
    if (this.opts.net && mine < 0) this.app.touch.fightMode = false;
    if (!(this.opts.net && mine < 0)) this.app.touch.fightMode = m.phase !== "over";
    m.update(dt);
    if (m.phase === "over" && !this.overHandled) {
      this.overHandled = true;
      if (this.opts.endMenu) {
        this.showEnd = true;
        if (DB.menuMusic.length) playMenuMusic(); else audio.stopMusic();
      } else if (this.opts.onOver) {
        this.overTimer = this.opts.overDelay ?? 0;
      }
    }
    if (this.overTimer !== undefined && this.overTimer !== null) {
      this.overTimer -= dt;
      if (this.overTimer <= 0) { this.overTimer = null; this.opts.onOver(m); }
    }
    if (this.showEnd) {
      const inp = this.app.anyInput;
      const items = this.endItems();
      if (inp.justPressed("up")) this.endIndex = (this.endIndex + items.length - 1) % items.length;
      else if (inp.justPressed("down")) this.endIndex = (this.endIndex + 1) % items.length;
      else if (ok(inp) && m.phaseT > 0.4) this.endPick(this.endIndex);
    }
  }

  pausePick(i) {
    if (i === 0) {
      this.paused = false;
      if (!this.opts.net) { audio.resumeSfx(); audio.resumeMusic(); }
    } else if (i === 1) {
      const me = this;
      this.app.setScene(new OptionsScene(this.app, { onBack: () => { me.app.setScene(me); me.paused = true; } }));
    } else {
      audio.resumeSfx();
      audio.stopAllSfx();
      this.cleanup();
      mainMenu(this.app);
    }
  }

  endPick(i) {
    this.showEnd = false;
    audio.stopAllSfx();
    if (this.opts.onEndChoice) this.opts.onEndChoice(i, this);
  }

  cleanup() { if (this.match.stage) this.match.stage.dispose(); }

  draw(ctx, view) {
    this.match.draw(ctx, view);
    const m = this.match;
    if (m.phase === "over") {
      const w = m.f[m.winner];
      const txt = `¡${w.name.toUpperCase()} GANA LA PELEA!`;
      if (this.showEnd) {
        // revancha: cuadro congelado + velo + título arriba + menú (igual que en PC)
        UI.overlay(ctx, view, 140 / 255);
        UI.pcTitle(ctx, view, txt, 70);
        UI.menuList(ctx, view, this.endItems(), this.endIndex, C.BASE_H / 2 + 60, (k) => { if (m.phaseT > 0.4) this.endPick(k); });
      } else {
        // Torre / torneo: pantalla oscura con el ganador (igual que en PC)
        ctx.fillStyle = COLORS.dark; ctx.fillRect(0, 0, view.w, C.BASE_H);
        UI.centerText(ctx, view, txt, COLORS.yellow);
        const msg = this.opts.overMessage ? this.opts.overMessage(m) : null;
        if (msg) UI.text(ctx, msg, view.w / 2, C.BASE_H / 2 + 60, { size: 20, shadow: false });
      }
    }
    if (this.paused) {
      UI.overlay(ctx, view, 0.7);
      UI.title(ctx, view, "PAUSA", 150, COLORS.yellow, 48);
      UI.menuList(ctx, view, this.pauseItems(), this.pauseIndex, 290, (k) => this.pausePick(k));
    }
  }
}

// ---------------------------------------------------------------------
// Pelea local genérica (versus / cpu) con revancha y cambio de personajes
// ---------------------------------------------------------------------
async function launchLocal(app, { slugs, mystery, stageDef, inputs, onChangeChars }) {
  const prep = await prepareFight(app, slugs, stageDef);
  const build = () => new Match({ entries: prep.entries, frames: prep.frames, stage: prep.stage, inputs, mystery });
  audio.stopAllSfx();
  playStageMusic(prep.stage);
  const scene = new FightScene(app, {
    match: build(), pausers: inputs.filter((i) => !i.thinkFight), endMenu: true,
    onEndChoice: (choice, sc) => {
      if (choice === 0) {
        if (inputs[1].thinkFight) inputs[1] = new CPUInput(inputs[1].difficulty);
        sc.match = build();
        sc.overHandled = false;
        playStageMusic(prep.stage);
      } else if (choice === 1) { sc.cleanup(); onChangeChars(); }
      else { sc.cleanup(); mainMenu(app); }
    },
  });
  app.setScene(scene);
}

export function startVersusLocal(app) {
  app.setScene(new CharSelectScene(app, {
    players: [{ input: app.inputs[0] }, { input: app.inputs[1] }],
    onBack: () => localMenu(app, 0),
    onDone: (picks) => app.setScene(new StageSelectScene(app, {
      input: app.inputs[0],
      onBack: () => startVersusLocal(app),
      onDone: (stageDef) => launchLocal(app, {
        slugs: picks.map((p) => p.slug), mystery: [false, false], stageDef,
        inputs: [app.inputs[0], app.inputs[1]], onChangeChars: () => startVersusLocal(app),
      }),
    })),
  }));
}

export function startCpuFight(app, level) {
  app.setScene(new CharSelectScene(app, {
    players: [{ input: app.inputs[0] }, { cpu: true }],
    onBack: () => onePlayerMenu(app, 1),
    onDone: (picks) => app.setScene(new StageSelectScene(app, {
      input: app.inputs[0],
      onBack: () => startCpuFight(app, level),
      onDone: (stageDef) => launchLocal(app, {
        slugs: picks.map((p) => p.slug), mystery: [false, false], stageDef,
        inputs: [app.inputs[0], new CPUInput(level)], onChangeChars: () => startCpuFight(app, level),
      }),
    })),
  }));
}

export { randomStage, secretStage };
