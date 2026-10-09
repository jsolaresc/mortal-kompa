"""
tournament.py
--------------
Motor del modo "Torneo" (Multijugador > Torneo): de 3 a 16 personajes
elegidos (pueden repetirse), eliminación directa por brackets. El
sorteo es al azar UNA SOLA VEZ, al armar el torneo (ver __init__) --
de ahí en más el bracket queda FIJO como cualquier llave de
eliminación directa de toda la vida: el ganador del partido 1 de cada
ronda juega contra el ganador del partido 2, el del partido 3 contra
el del partido 4, y así sucesivamente (ver _start_round). Si en algún
momento queda una cantidad impar de peleadores, uno pasa directo a la
siguiente ronda sin pelear (el bye, siempre el último de la lista).

Esta clase SOLO maneja los datos/la lógica del torneo (quién pelea
contra quién, quién ganó, quién es el campeón) -- el dibujo del
bracket en pantalla (animaciones de subida/caída, etc.) está en
engine/menu.py (TournamentBracketScreen), y las peleas en sí las
maneja main.py con el mismo motor de pelea de siempre (2 Jugadores).
"""

import random


def label_picks(picks):
    """Le pone a cada elección un "label" único (ej. "Nico", "Nico 2",
    "Nico 3") cuando un mismo personaje se repite -- se usa acá (para
    los que ya se van a pelear) y en vivo, mientras se están eligiendo
    (ver TournamentCharacterSelect en engine/menu.py), para que la lista
    de "Personajes elegidos" ya muestre la numeración correcta apenas se
    confirma cada uno, no recién al terminar de armar el torneo."""
    counts = {}
    labeled = []
    for p in picks:
        if p.get("label"):
            # ya viene con su etiqueta definitiva (torneo por WiFi:
            # "Ana · J2", el número de jugador ya los distingue)
            labeled.append(dict(p))
            continue
        counts[p["json_path"]] = counts.get(p["json_path"], 0) + 1
        n = counts[p["json_path"]]
        label = p["name"] if n == 1 else f"{p['name']} {n}"
        labeled.append({**p, "label": label})
    return labeled


class TournamentBracket:
    def __init__(self, picks, keep_order=False):
        """picks: lista de dicts de personaje (load_character_list), en
        el orden en que se eligieron -- pueden repetirse. Cada entrada
        del torneo lleva un "label" único (ej. "Nico", "Nico 2", "Nico
        3") para poder distinguirlos en el bracket y en los anuncios."""
        self.entrants = label_picks(picks)

        self.round_number = 1
        self.champion = None
        self.bye = None
        self.matches = []
        self.match_index = 0
        self.round_results = []
        # Rondas ya terminadas (no se pisan al arrancar la siguiente) --
        # sin esto, al llegar a la Ronda 2 no había forma de saber a
        # quién le había ganado cada uno en la Ronda 1 (bug reportado:
        # "ya no veo quiénes perdieron en la ronda 1"). Cada elemento:
        # {"round_number", "matches", "bye", "results"}.
        self.history = []
        # ÚNICO sorteo al azar de todo el torneo: arma el orden inicial
        # del bracket acá, una sola vez -- de ahí en más (ver
        # _start_round) el orden queda FIJO, el ganador del partido 1
        # siempre juega contra el ganador del partido 2, etc., como en
        # cualquier llave de eliminación directa (antes se volvía a
        # sortear en CADA ronda, algo que no correspondía -- bug
        # reportado: "el sorteo de cada ronda no debería ser al azar").
        seeded = list(self.entrants)
        if not keep_order:
            # keep_order=True: el orden ya viene sorteado (el invitado de
            # un torneo por WiFi arma una copia EXACTA del bracket del
            # anfitrión, ver engine/net_screens.py)
            random.shuffle(seeded)
        self.seeded = list(seeded)
        self._start_round(seeded)

    def _start_round(self, participants):
        """Arranca la ronda siguiente con los que ganaron (o pasaron por
        bye) la ronda anterior, EN EL MISMO ORDEN en que vienen -- NO
        se vuelven a mezclar acá. El único sorteo al azar de todo el
        torneo es el que arma el orden inicial, en __init__: de ahí en
        más, el ganador del partido 1 de esta lista juega contra el
        ganador del partido 2, el del partido 3 contra el del partido
        4, y así sucesivamente -- el bracket queda fijo desde el
        principio, como cualquier llave de eliminación directa."""
        participants = list(participants)
        self.bye = None
        if len(participants) % 2 == 1:
            self.bye = participants.pop()
        self.matches = [participants[i:i + 2] for i in range(0, len(participants), 2)]
        self.match_index = 0
        self.round_results = []


    def current_match(self):
        """Devuelve (entrant_a, entrant_b) de la pelea que sigue, o None
        si ya se jugaron todas las de esta ronda."""
        if self.match_index < len(self.matches):
            return tuple(self.matches[self.match_index])
        return None

    def peek_upcoming(self, count=3):
        """Próximas peleas de ESTA ronda (para mostrar a los costados del
        bracket mientras se juega la actual)."""
        return [tuple(m) for m in self.matches[self.match_index + 1: self.match_index + 1 + count]]

    def matches_remaining_this_round(self):
        return len(self.matches) - self.match_index

    def is_final_match(self):
        """True si la pelea actual es LA final del torneo (ganarla
        corona campeón/a directo, sin necesitar otra ronda más) -- se
        usa para que esa pelea puntual sea siempre en Final Destination,
        igual que el jefe final de la Torre de Batalla, y para que el
        título de la pantalla diga "FINAL" en vez de "RONDA N"."""
        return len(self.matches) == 1 and self.bye is None

    def find_previous_match(self, entrant):
        """Busca, en la ÚLTIMA ronda ya terminada, el cruce del que vino
        'entrant' -- para poder mostrarlo en el bracket de la ronda
        actual (a quién le ganó para llegar hasta acá). Devuelve
        (perdedor, ganador) o None si 'entrant' pasó de ronda por bye,
        o si esta es la primera ronda (no hay historial todavía)."""
        if not self.history:
            return None
        return self.find_match_at_history_index(entrant, len(self.history) - 1)

    def find_match_at_history_index(self, entrant, hist_idx):
        """Como find_previous_match, pero para CUALQUIER ronda ya
        jugada (no solo la última): 'hist_idx' es el índice dentro de
        self.history (0 = Ronda 1, 1 = Ronda 2, ...). Se usa para
        reconstruir todo el linaje de un peleador, ronda por ronda,
        hasta la Ronda 1 -- así el bracket de una ronda avanzada puede
        seguir mostrando TODO el recorrido completo, no solo un
        escalón para atrás (pedido explícito: que sea "el mismo
        bracket" de la Ronda 1, con los personajes avanzando adentro
        suyo, en vez de un bracket nuevo y más chico cada ronda).
        Devuelve (perdedor, ganador) o None si 'entrant' tuvo bye esa
        ronda, o si el índice no existe."""
        if hist_idx < 0 or hist_idx >= len(self.history):
            return None
        rnd = self.history[hist_idx]
        if rnd["bye"] is not None and rnd["bye"]["label"] == entrant["label"]:
            return None
        for i, pair in enumerate(rnd["matches"]):
            winner = rnd["results"][i]
            if winner["label"] == entrant["label"]:
                loser = pair[1] if winner is pair[0] else pair[0]
                return (loser, winner)
        return None

    def report_result(self, winner_entrant):
        """Se llama al terminar una pelea. Devuelve True si el torneo
        TERMINÓ (ya hay campeón), False si hay que seguir jugando."""
        self.round_results.append(winner_entrant)
        self.match_index += 1
        if self.match_index >= len(self.matches):
            # El bye (si hay) se agrega DESPUÉS de todos los ganadores
            # de los partidos, nunca antes -- así, en la ronda
            # siguiente, se empareja con el ganador del ÚLTIMO partido
            # de esta ronda (los primeros se emparejan entre sí, de a
            # dos, en orden) en vez de con el del primero. Antes el bye
            # se agregaba adelante de todo (armado en _start_round), lo
            # que lo emparejaba con el ganador del PRIMER partido de la
            # ronda siguiente -- no coincidía con cómo tenía que verse
            # el bracket (pedido explícito, con capturas de referencia
            # hechas a mano: el bye espera "un escalón arriba" y se
            # cruza con el último cruce disponible, no con el primero).
            if self.bye is not None:
                self.round_results.append(self.bye)
            self.history.append({
                "round_number": self.round_number,
                "matches": list(self.matches),
                "bye": self.bye,
                "results": list(self.round_results),
            })
            if len(self.round_results) == 1:
                self.champion = self.round_results[0]
                return True
            self.round_number += 1
            self._start_round(self.round_results)
        return False
