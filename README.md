# Saturn Gauss — commandement orbital de Saturne

An 2150. Vous commandez le **canon de Gauss interplanétaire** qui orbite autour de Saturne, ainsi que
six **stations de défense** dispersées autour de la planète. Tout se joue dans **une seule session** :
défendre Saturne contre des vaisseaux, détruire des flottes lointaines à coups de bombes, dévier des
astéroïdes, frapper des cibles planétaires — en gérant argent, munitions, énergie et réparations.

## Lancer

```bash
pip install -r requirements.txt
python main.py                   # jeu complet
python main.py --no-assist       # sans ordinateur de visée interplanétaire (expert)
python main.py --save-plots      # graphes en PNG (plots/) au lieu de fenêtres
python main.py --seed 42         # graine du hasard (événements reproductibles)
python main.py --load partie     # charge saves/partie.pkl
python -m pytest -m "not slow"   # tests rapides (2 s) ; sans -m : tout (~25 s)
```

## Le jeu en bref

| Ce qui arrive | Type | Vous pouvez refuser ? | Avec quoi tirer |
|---|---|---|---|
| Vaisseaux ennemis qui attaquent Saturne (⚠) | événement prioritaire | **non** | une station (ou le canon) |
| Astéroïde en route vers une colonie alliée (⚠) | événement prioritaire | **non** | le canon interplanétaire |
| Flotte stationnée / en assaut autour d'une autre planète | contrat | oui | canon interplanétaire + bombe |
| Astéroïde (contrat bonus), frappes planétaires (6 missions) | contrat | oui | canon interplanétaire |

Le temps est unique et continu : si vous passez des semaines à préparer une frappe, une attaque
prioritaire *interrompt* l'attente (`wait`, `plan`) et se déroule sans vous si vous l'ignorez
(vos stations encaissent, les vaisseaux atteignent Saturne, vous payez la pénalité).
On change de tireur et de munition **à la volée**, selon le contrat : `use <n>`, `ammo <type>`.

### Défendre Saturne (la boucle principale, sans hasard)
1. `board` puis `focus <n>` sur l'attaque. `ships` liste les vaisseaux, `ship <n>` dessine leurs **composants**
   (boîtes) vus du tireur courant ; `view` ouvre une fenêtre graphique (couleur = intégrité, bulle = bouclier).
2. `target 1.reactor` (ou `target 1.3`) désigne une pièce. Le jeu donne sa **position** `P` et sa **vitesse** `V`
   (repère centré sur Saturne, km), la position de la station `S`, la distance `d` et la durée de vol `tau = d / vp`.
3. `stations` montre, pour chaque station, si la pièce est **dégagée** ou **masquée** (par une autre pièce ou par
   Saturne). Choisissez la station qui voit votre cible : `use <n>`.
4. **Calculez l'orientation** : le projectile va en ligne droite à 50-95 % de c, mais la cible bouge pendant
   le vol. Point à viser `A = P + V·tau` ; longitude `atan2(Ay-Sy, Ax-Sx)`, latitude `asin((Az-Sz)/|A-S|)`.
   `calc` est une calculatrice avec ces variables (`calc atan2(1,2)`). Précision typique : 10⁻⁵ à 10⁻⁶ degré.
   (`solve` fait le calcul pour vous contre 150 cr.)
5. Choisissez la munition et la masse, `set vitesse 0.7c` (ou `70%`, ou km/s), `aim <lon> <lat>`, `fire`.
   En cas de raté, le jeu donne l'**écart** en mètres dans le repère du vaisseau (avant / gauche / haut) pour corriger.
6. Le vaisseau réagit : bouclier, composants détruits, riposte sur vos stations. Recommencez.

**Vaisseaux** : capitale, destroyer, frégate, corvette, patrouilleur, transport de troupes, minier, soutien.
Chaque classe a un bouclier (énergie dissipée, qui se régénère), une coque en composants (pont, **réacteur**
critique, générateur de bouclier, moteurs, batteries, cales…), un blindage, une prime. Détruire le réacteur
détruit le vaisseau ; détruire le pont le neutralise (70 % de la prime) ; un équipage gazé le fait capturer (150 %).
Les batteries détruites réduisent sa riposte, le générateur détruit coupe le bouclier.

**Munitions** (`ammo`) :

| clé | effet |
|---|---|
| `rod` tungstène | polyvalente, pénètre selon sa **longueur** |
| `ferrite` | sature les boucliers (x4), peu efficace sur la coque |
| `ap_he` perforant-explosif | pic (x3 de pénétration) puis ogive qui explose à l'intérieur (x2,5) + dégâts voisins |
| `dirty` projectile sale | fragmentation : dégâts de zone, détonation de proximité contre les flottes |
| `gas` | traverse les boucliers, neutralise l'équipage |
| `nuke`, `antimatter` | bombes (canon interplanétaire uniquement) |
| `beam` | impulsion laser |

**Lanceurs** : Gauss orbital (50-95 % de c, ≤ 5 kg), railgun (50-99 % de c, ≤ 15 kg, énergivore), laser
(instantané, pas de munition), obusier à poudre (2-15 km/s, très courte portée), canon interplanétaire
(jusqu'à c). `buy rail|laser` puis `refit <station> <lanceur>`.

### Frapper loin : flottes, astéroïdes, planètes
Le canon interplanétaire tire à n'importe quelle vitesse **jusqu'à c** (énergie cinétique relativiste
`(γ-1)mc²`, composition relativiste des vitesses avec le canon qui file à ~20 km/s, gravité post-newtonienne).
- **Flotte ennemie** (élimination / protection) : bombe `nuke` ou `antimatter` à **détonation de proximité**.
  Dégâts `E ∝ 1/d²` sur chaque vaisseau (bouclier d'abord, puis composants). Il faut arriver avant l'échéance : tirez vite.
  Les survivants peuvent **riposter** sur Saturne (nouvel événement).
- **Astéroïde** : un projectile cinétique transmet de la quantité de mouvement (`Δv = (1+β)·γmv/M`). Il faut
  que la distance de passage dépasse 1,3 fois le rayon critique de la planète (focalisation gravitationnelle incluse).
  *Pourquoi une colonie et pas Saturne ?* Tiré depuis Saturne, un projectile frappe un astéroïde qui vise Saturne
  **de face** : un retard ne dévie pas sa trajectoire relative. Les astéroïdes menacent donc les colonies alliées.
- **Frappes planétaires** : un point précis (lat/lon) d'une planète qui tourne, avec énergie, pénétration, délai.

**Ordinateur de visée interplanétaire** (payant, facultatif) :
`window` cherche les dates de tir pour **votre vitesse et votre barre** (`window auto` = vitesse optimale,
`window 3` = vol de 3 jours max) ; `plan <n>` charge la fenêtre ; `refine` corrige par tirs d'essai (Newton/Broyden)
la direction et l'heure de tir pour viser le point exact, **sans toucher à votre vitesse ni à votre barre**.

### Économie
Crédits au départ : 60 000. Un tir coûte **munition + énergie** (`cost`). Les stations touchées coûtent des
réparations (`repair <n|all>`). `upgrades` / `buy <clé>` : vitesse max, masse max, cadence, blindage, boucliers,
alimentation du canon, ordinateur de bord (-25 % de frais), nouveaux lanceurs. `save` / `load`, scores dans `saves/scores.json`.
Les chiffres d'équilibrage sont dans `economy.py`, `combat/ships.py`, `combat/ammo.py`, `combat/launchers.py`.

## Organisation du projet

```
saturn_gauss/
├── main.py
├── saturn_gauss/
│   ├── constants.py  timeutils.py  main.py
│   ├── solarsystem/          Soleil + 8 planètes : orbites képlériennes 3D, rotation propre (IAU)
│   ├── ballistics/           projectile (relativiste), canon, intégrateur RK4 post-newtonien, Lambert, Kepler 2 corps
│   ├── targets.py            cibles : point de surface, flotte en orbite, astéroïde
│   ├── guidance.py           fenêtres de tir (vitesse du joueur ou auto), correction par tirs d'essai
│   ├── combat/               géométrie de rayons, vaisseaux à composants, munitions, dégâts, lanceurs,
│   │                         stations, engagement (anticipation, occlusion, visée), vagues ennemies
│   ├── contracts.py          contrats, événements prioritaires, générateurs
│   ├── economy.py            crédits, coûts, améliorations
│   ├── career.py             le monde : temps, événements, tirs, boutique, sauvegarde
│   ├── game/missions.py      les 6 frappes planétaires de la campagne
│   └── ui/                   shell (terminal.py), tableaux, vue des vaisseaux (ASCII + matplotlib), graphes
└── tests/                    pytest : monde, balistique relativiste, combat, carrière, scénarios de bout en bout
```

## Simplifications assumées
- Combat en ligne droite (la gravité de Saturne est négligée pour les projectiles de station) ; les vaisseaux suivent
  une hyperbole képlérienne autour de Saturne ; les stations sont sur des orbites circulaires.
- Pas de lunes, d'atmosphères ni d'anneaux ; planètes sphériques ; Soleil fixe pour les planètes.
- Les plages de vitesse des stations (50-95 % de c) suivent la description de gameplay ; modifiez `combat/launchers.py`
  pour tester « < 50 % de c ».
- `eval` restreint pour `calc` (jeu local).

## Ce que l'on peut faire
Pour les mission de destruction de vaisseau qui attaque la planete j'aimerais que les vaisseau ait des bouclier capable de dissipé une certaine quantité d'énérgie puis que il y ait la coque dérière et que les vaisseau soit divisé en plusieur partie qui changerait en fonction de la classe du vaisseau. Que certain projectile soit plus effiace contre les boucliers ou la coque. Par exemple un prejectile contenant de la férite cappable de dissipé les boucliers ou bien une barre en tungstène avec d'abord un pic pour transpèrsé la coque puis une ogive pour faire explosé l'intérieur du vaisseau.

J'aimerais qu'il y ait un autre type d'attaque de vaisseau. Celui qui passent par les contract et qui attaque une autre planete que la notre et donc beaucoup trop loin pour que les canon orbitaux de défense les attaque. Il faudra alors utilisé le canon intérplanétaire pour envoiyer une bombe nucleaire ou à antimatière pour faire explosé le groupe de vaisseau. Les vaisseau enemie pourrait aussi nous attaqué il faudrait donc bien choissir quelle partie du vaisseau détruire en premier pour être le plus éfficase. Si une station est détruite ou endomagé il faudra alors la réparer et cela coutera de l'argent. Tout comme les projectile et l'energie utilisé pour les tiré qui ne sont pas gratuit.

J'aimerais qu'il y ait plusieur type de vaisseau : Classe capitale (les plus gros), destroyer, transport de troupe, minié, patrouilleur, soutien, corvette, frégate etc

Les projectile tiré par les station orbital sont beaucoup plus petit (ayant une taille max) mais toujour très rapide (< à 50% de c)

les station de défense orbital serait plus nombreuse et dispérsé tout autour de la planète. On pourra donc choisir la quelle on souhaite pour executé la mission.

J'aimerais que tout cela tourne sur la même partie, c'est a dire pas besoin d'aller dans un menu pour changé le mode de jeu. Je prefererais que l'on puissent choisir avec quoi tiré en fonction de la mission dinamiquement. Que l'on puissent dire oui ou bien refusé un contract mais pas les mission prioritaire comme les attaque de vaisseau enemie sur la planète ou bien les asteroide.

Le canon inter planetaire devra tiré des projectiles plus rapide et les mission demander plus d'énérgie pour évité des année de voyage.

Au niveau du gameplay il faudrait quelque chose de beaucoup moins basé sur la chance et deanderais peut etre a faire un peu de calcule si necessaire. Imaginons qu'une mission prioritaire d'un destroyer qui arrive sur la planete. Sont angle d'arrivé et alors indiqué. On sélectionne la station de défense qui correspond le mieux a l'angle de tire. Depuis cette station il faudrait qu'il s'affiche sur notre interface le vaisseau fait de boite qui correspond au different composant de celui-ci que l'on peut detruire. On peut alors en selectionné un et le jeu nous donne des coordonné par rapport à la planete et il est alors a nous de calculer l'orientation de la station. Il nous faut alors ensuite choisir le projectile. La vitesse des projectile etant très grande on peut considére qu'il vont en ligne droite alors on choisi la vitesse entre 50 et 95 % de c et on fait feu puis on voit comment la cible réagit et on recommence.

## Pistes d'extension restantes
Lunes (Titan, Lune) comme bases ou cibles ; cibles gazeuses (ciblage « plan B » plutôt qu'un point à date fixe) ;
perturbations Soleil-barycentre ; interface `curses` ; canon orbital tirant sur le sol ; convois à protéger ;
gestion de ressources (stock de munitions, usine) ; vaisseaux ennemis qui manœuvrent ; équipes de réparation.

Quand un vaisseau nous attaque, l'utilisation d'une bombe atomique pour désactivé les bouclier du vaisseau porrait etre utilisale. On devrais calculer le temps avant l'explosion et le rentré à la main. Car pour que la bombe soit efficase contre les bouclier il faudrait que la bombe explose avant les bouclier dans un intervalle de 50m-500m avant les bouclier, il nous faudrait alors determiner à la main le temps avant la détonation en fonction de la distance et de la vitesse du projectile.