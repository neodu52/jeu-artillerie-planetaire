# Saturn Gauss — l'artilleur du futur

An 2150. Un gigantesque **canon de Gauss** orbite autour de Saturne et tire des barres de tungstène
sur les autres planètes. Vous réglez tout : dimensions de la barre, vitesse, orientation, **moment du tir**.
Chaque mission impose une cible (un point précis à la surface d'une planète en rotation) et une énergie.
À vous de calculer la trajectoire dans un **système solaire 3D entièrement simulé**.

## Lancer

```bash
pip install -r requirements.txt
python main.py                 # jeu complet, avec ordinateur de visée
python main.py --no-assist     # mode expert : tout calculer soi-même
python main.py --save-plots    # graphes en PNG (dossier plots/) au lieu de fenêtres
python main.py --mission 4     # démarrer à une mission donnée
python -m pytest -m "not slow" # tests rapides  (sans -m : tout, ~2 min)
```

## Organisation du projet

```
saturn_gauss/
├── main.py                       point d'entrée
├── saturn_gauss/
│   ├── constants.py  timeutils.py
│   ├── solarsystem/              LE MONDE
│   │   ├── bodies.py             données physiques + éléments orbitaux + rotation (IAU)
│   │   ├── kepler.py             éphémérides képlériennes 3D vectorisées (position + vitesse)
│   │   ├── rotation.py           rotation propre : lat/lon de surface <-> repère inertiel
│   │   └── system.py             SolarSystem : Soleil + 8 planètes
│   ├── ballistics/               LA PHYSIQUE DU TIR
│   │   ├── projectile.py         barre de tungstène : masse, énergie, pénétration
│   │   ├── cannon.py             canon en orbite circulaire autour de Saturne
│   │   ├── integrator.py         RK4 à pas adaptatif, gravité N-corps, détection d'impact
│   │   └── lambert.py            solveur de Lambert (variables universelles)
│   ├── guidance.py               ordinateur de visée : fenêtres, hyperbole d'évasion, correction
│   ├── game/
│   │   ├── missions.py           campagne (6 missions)
│   │   └── state.py              Game : réglages, tir, évaluation, score
│   └── ui/
│       ├── terminal.py           REPL (cmd.Cmd)
│       ├── formatting.py         tableaux, carte ASCII, rapports
│       └── plots.py              graphes matplotlib (2D, 3D, approche)
└── tests/                        pytest : monde, balistique, missions de bout en bout
```

## Le modèle physique

| Élément | Modèle |
|---|---|
| Planètes | orbites képlériennes **inclinées** (éléments de Standish/JPL avec dérivées séculaires), repère écliptique J2000 |
| Rotation propre | pôle et méridien origine IAU, vitesse en °/jour (Vénus et Uranus rétrogrades), axes inclinés |
| Canon | orbite circulaire de 300 000 km autour de Saturne (période 46,6 h), dans son plan équatorial |
| Projectile | particule test attirée par le Soleil **et** les 8 planètes (Saturne incluse au départ) |
| Intégration | RK4, pas adapté à la distance et au temps de chute libre du corps le plus proche |
| Impact | interpolation dans le repère de la planète, latitude/longitude exactes, vitesse relative |
| Énergie | `E = ½ m v²` à la bouche, `m = ρ·π·r²·L` (ρ = 19 250 kg/m³) |
| Pénétration | limite hypervitesse `L·√(ρ_barre/ρ_roche)` |

Approximations assumées : pas de lunes, pas d'atmosphères ni d'anneaux, planètes sphériques, Soleil fixe
(les perturbations planète-planète sont ignorées pour les planètes, pas pour le projectile),
le recul est affiché mais la station le compense.

## Jouer

Le repère de visée est **écliptique héliocentrique** : longitude 0° vers l'équinoxe, latitude +90° vers le pôle nord écliptique.
La vitesse de bouche est relative au canon, qui file lui-même à 11,25 km/s autour de Saturne et à ~9,7 km/s autour du Soleil.

**Ce qu'il faut maîtriser**
1. *Énergie* : `E = ½ m v²` fixe le compromis masse / vitesse (`match vitesse|rayon`).
2. *Vitesse* : pour aller vers l'intérieur du système il faut annuler une partie de la vitesse orbitale de Saturne, après s'être extrait de son puits de gravité.
3. *Date de tir* : les planètes bougent ; le canon tourne en 46 h, ce qui change la vitesse de bouche nécessaire.
4. *Arrivée* : la cible tourne sur elle-même. Il faut arriver quand le point visé fait face au projectile.
5. *Précision* : une erreur de 10⁻⁵ rad à la sortie fait plus de 10 000 km d'erreur à l'arrivée.

**Ordinateur de visée (optionnel, pénalise le score)**
`window` → liste de fenêtres (conique raccordée, Lambert) · `plan n` → charge le tir · `refine` → tirs d'essai (Newton/Broyden)
sur la vraie simulation jusqu'à viser le point exact. `refine <date d'arrivée>` corrige aussi *vos* réglages manuels.

Session type :
```
> window
> plan 1
> refine
> fire  
```

Missions : Olympus Mons (Mars) · Caloris (Mercure) · Maxwell Montes (Vénus, rotation rétrograde de 243 j) ·
Bunker de Hellas (pénétration ≥ 25 m) · pôle nord de Mercure (précision 100 km) · Valles Marineris (délai ≤ 1400 j).

## Pistes d'extension
Lunes (Titan, Lune), cibles gazeuses (nécessite un ciblage en plan B plutôt qu'un point à date fixe),
perturbations Soleil-barycentre, cibles mobiles, sauvegarde des scores, interface `curses`, visualisation des changement dans une fenetre, autre type de canon (laser, a poudre, railgun avec conso d'energie etc), autre mode de jeu (canon en orbite qui tire sur le sol, canon orbital qui tire sur vaisseau), autre moyen de jouer pour le mode planete-planete car celui ci est basé sur la chance ou l'utilisation de l'ordinateur de bord, systeme d'amélioration, gestion de ressource, utilisation d'autre bibliotéque si nécessaire, autre projectile en fonction de la mission(gaz, antiblindage, projectile sale à la façon des bombe mais sans explosion atomique, projectile à antimatiere et autre), mission de déroutage d'astéroide, contract de protection ou d'élimination.

Pour les mission de destruction de vaisseau qui attaque la planete j'aimerais que les vaisseau ait des bouclier capable de dissipé une certaine quantité d'énérgie puis que il y ait la coque dérière et que les vaisseau soit divisé en plusieur partie qui changerait en fonction de la classe du vaisseau. Que certain projectile soit plus effiace contre les boucliers ou la coque. Par exemple un prejectile contenant de la férite cappable de dissipé les boucliers ou bien une barre en tungstène avec d'abord un pic pour transpèrsé la coque puis une ogive pour faire explosé l'intérieur du vaisseau.

J'aimerais qu'il y ait un autre type d'attaque de vaisseau. Celui qui passent par les contract et qui attaque une autre planete que la notre et donc beaucoup trop loin pour que les canon orbitaux de défense les attaque. Il faudra alors utilisé le canon intérplanétaire pour envoiyer une bombe nucleaire ou à antimatière pour faire explosé le groupe de vaisseau.
Les vaisseau enemie pourrait aussi nous attaqué il faudrait donc bien choissir quelle partie du vaisseau détruire en premier pour être le plus éfficase. Si une station est détruite ou endomagé il faudra alors la réparer et cela coutera de l'argent. Tout comme les projectile et l'energie utilisé pour les tiré qui ne sont pas gratuit.

J'aimerais qu'il y ait plusieur type de vaisseau : Classe capitale (les plus gros), destroyer, transport de troupe, minié, patrouilleur, soutien, corvette, frégate etc

Les projectile tiré par les station orbital sont beaucoup plus petit (ayant une taille max) mais toujour très rapide (< à 50% de c)

les station de défense orbital serait plus nombreuse et dispérsé tout autour de la planète. On pourra donc choisir la quelle on souhaite pour executé la mission.

J'aimerais que tout cela tourne sur la même partie, c'est a dire pas besoin d'aller dans un menu pour changé le mode de jeu. Je prefererais que l'on puissent choisir avec quoi tiré en fonction de la mission dinamiquement. Que l'on puissent dire oui ou bien refusé un contract mais pas les mission prioritaire comme les attaque de vaisseau enemie sur la planète ou bien les asteroide.

Le canon inter planetaire devra tiré des projectiles plus rapide et les mission demander plus d'énérgie pour évité des année de voyage.

Au niveau du gameplay il faudrait quelque chose de beaucoup moins basé sur la chance et deanderais peut etre a faire un peu de calcule si necessaire. Imaginons qu'une mission prioritaire d'un destroyer qui arrive sur la planete. Sont angle d'arrivé et alors indiqué. On sélectionne la station de défense qui correspond le mieux a l'angle de tire. Depuis cette station il faudrait qu'il s'affiche sur notre interface le vaisseau fait de boite qui correspond au different composant de celui-ci que l'on peut detruire. On peut alors en selectionné un et le jeu nous donne des coordonné par rapport à la planete et il est alors a nous de calculer l'orientation de la station. Il nous faut alors ensuite choisir le projectile. La vitesse des projectile etant très grande on peut considére qu'il vont en ligne droite alors on choisi la vitesse entre 50 et 95 % de c et on fait feu puis on voit comment la cible réagit et on recommence.

Quand un vaisseau nous attaque, l'utilisation d'une bombe atomique pour désactivé les bouclier du vaisseau porrait etre utilisale. On devrais calculer le temps avant l'explosion et le rentré à la main. Car pour que la bombe soit efficase contre les bouclier il faudrait que la bombe explose avant les bouclier dans un intervalle de 50m-500m avant les bouclier, il nous faudrait alors determiner à la main le temps avant la détonation en fonction de la distance et de la vitesse du projectile.