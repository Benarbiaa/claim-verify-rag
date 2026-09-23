# Cahier des Charges
## Système de RAG Agentique avec Vérification de Véracité (Claim Verification)

**Auteur :** Emir Benarbia
**Contexte :** Projet technique personnel — préparation à la recherche de stage de fin d'études (PFE), janvier–juin 2027
**Domaine :** IA appliquée — RAG, systèmes agentiques, NLP
**Date :** Septembre 2026

---

## 1. Contexte et motivation

### 1.1 Problème adressé
Les systèmes RAG (Retrieval-Augmented Generation) classiques souffrent d'un défaut structurel : ils font confiance aveuglément aux passages récupérés, sans vérifier si la réponse générée est réellement **fidèle** (faithful) aux sources, ni si les sources elles-mêmes sont **cohérentes entre elles**. Ce problème — les hallucinations et les affirmations non vérifiées — est aujourd'hui l'un des principaux freins à l'adoption des systèmes RAG en production, notamment dans des domaines sensibles (recherche académique, juridique, médical).

### 1.2 Objectif du projet
Concevoir et implémenter un système agentique qui, au lieu de répondre directement à partir des passages récupérés, **décompose sa propre réponse en affirmations vérifiables (claims)**, les confronte individuellement aux sources, détecte les contradictions ou les affirmations non supportées, et restitue une réponse annotée par niveau de confiance.

### 1.3 Valeur différenciante
- Aborde un problème réel et actuel (faithfulness verification) recherché par les équipes IA en entreprise, pas un exercice académique isolé.
- Combine NLP classique (segmentation de phrases, NER, décomposition de claims) et architecture agentique moderne (orchestration multi-étapes, boucles d'outils).
- Comporte un volet évaluation rigoureux, rarement présent dans les projets étudiants.

---

## 2. Périmètre du projet

### 2.1 Inclus dans le périmètre
- Pipeline d'ingestion et d'indexation d'un corpus de papiers académiques (5 à 15 papiers dans un domaine choisi, ex. NLP/IA)
- Système de retrieval (base vectorielle)
- Agent orchestrateur : retrieve → générer une réponse brouillon → décomposer en claims → vérifier chaque claim → produire une réponse finale annotée
- Module de décomposition de claims (à partir de la réponse générée)
- Module de vérification : pour chaque claim, retrouver le(s) passage(s) source(s) le(s) plus pertinent(s) et déterminer un verdict (**supporté** / **contredit** / **non vérifiable**)
- Jeu d'évaluation constitué manuellement (20 à 30 questions), incluant des cas où la réponse doit légitimement contenir une contradiction ou une incertitude
- Interface minimale (CLI ou petite UI web) pour interroger le système et visualiser les claims + verdicts
- Rapport technique documentant les choix d'architecture et les résultats d'évaluation

### 2.2 Hors périmètre (explicitement exclu)
- Fine-tuning d'un modèle de langage (utilisation d'un LLM via API uniquement)
- Support multi-langue ou multi-domaine simultané
- Interface utilisateur avancée (pas de design produit poussé)
- Déploiement en production / scalabilité à grande échelle
- Support de corpus dynamiques (mise à jour en temps réel du corpus)

---

## 3. Exigences fonctionnelles

| ID | Exigence | Priorité |
|---|---|---|
| EF-1 | Le système doit ingérer un corpus de documents PDF et les découper en chunks indexables | Haute |
| EF-2 | Le système doit indexer les chunks dans une base vectorielle et permettre une recherche sémantique | Haute |
| EF-3 | L'agent doit générer une réponse brouillon à une question utilisateur à partir des passages récupérés | Haute |
| EF-4 | L'agent doit décomposer la réponse brouillon en une liste d'affirmations atomiques (claims) | Haute |
| EF-5 | Pour chaque claim, l'agent doit rechercher les passages sources les plus pertinents (retrieval ciblé) | Haute |
| EF-6 | L'agent doit attribuer un verdict à chaque claim : supporté, contredit, ou non vérifiable | Haute |
| EF-7 | Le système doit produire une réponse finale annotée, indiquant le niveau de confiance par affirmation | Haute |
| EF-8 | Le système doit permettre de comparer plusieurs passages sources en cas de contradiction potentielle entre documents | Moyenne |
| EF-9 | Le système doit exposer une trace de son raisonnement (quel passage a été utilisé pour quel claim) | Moyenne |
| EF-10 | Le système doit permettre d'injecter des contradictions synthétiques dans le corpus pour tester la détection | Moyenne |

---

## 4. Exigences non fonctionnelles

| ID | Exigence |
|---|---|
| ENF-1 | Le code doit être modulaire (ingestion / retrieval / agent / vérification séparés) pour faciliter la présentation et la maintenance |
| ENF-2 | Le temps de réponse par requête ne doit pas dépasser ~30 secondes en usage démo (pas d'exigence de production) |
| ENF-3 | Le système doit être reproductible : environnement documenté (dépendances, versions) |
| ENF-4 | Les coûts d'API LLM doivent rester maîtrisés (corpus volontairement restreint, mise en cache des embeddings) |
| ENF-5 | Le projet doit être versionné sur Git avec un historique de commits clair (utile pour montrer la démarche en entretien) |

---

## 5. Architecture proposée (vue d'ensemble)

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Corpus PDF  │ --> │  Ingestion    │ --> │  Base vectorielle │
└─────────────┘     │  (chunking,   │     │  (embeddings)     │
                     │  métadonnées) │     └─────────────────┘
                     └──────────────┘              │
                                                     ▼
┌───────────────────────────────────────────────────────────┐
│                      Agent orchestrateur                    │
│  1. Retrieval initial (question utilisateur)                │
│  2. Génération réponse brouillon                            │
│  3. Décomposition en claims atomiques                       │
│  4. Pour chaque claim : retrieval ciblé + vérification       │
│  5. Agrégation : réponse finale annotée + verdicts           │
└───────────────────────────────────────────────────────────┘
                                                     │
                                                     ▼
                                        ┌───────────────────────┐
                                        │  Réponse annotée +      │
                                        │  trace de raisonnement  │
                                        └───────────────────────┘
```

### Composants techniques envisagés (à valider en phase de conception détaillée)
- **Base vectorielle :** Qdrant ou pgvector
- **Embeddings :** modèle d'embedding via API ou open-source (à comparer)
- **LLM :** via API (Claude)
- **Décomposition de claims :** prompt structuré + éventuellement segmentation NLP classique en amont (réutilisation possible des TP de prétraitement)
- **Orchestration agentique :** boucle d'outils simple (pas de framework lourd nécessaire au départ — orchestration codée à la main pour garder le contrôle et pouvoir l'expliquer en entretien)

---

## 6. Méthodologie d'évaluation

### 6.1 Jeu de test
- 20 à 30 paires question/réponse construites manuellement à partir du corpus
- Inclure délibérément :
  - Des questions dont la réponse est clairement supportée par une source unique
  - Des questions nécessitant l'agrégation de plusieurs passages
  - Des questions où deux passages du corpus se contredisent (contradictions injectées ou naturelles)
  - Des questions dont la réponse n'est pas présente dans le corpus (doit être détecté comme non vérifiable)

### 6.2 Métriques
- **Précision de retrieval** (les bons passages sont-ils récupérés ?)
- **Précision de détection des claims non supportés** (rappel/précision sur les cas de contradiction injectée)
- **Taux de faux positifs** (claims correctement supportés mais marqués à tort comme contredits)
- Analyse qualitative de quelques cas d'échec (essentielle pour le rapport)

---

## 7. Livrables

1. Code source versionné (dépôt Git)
2. Corpus de test + jeu d'évaluation (questions/réponses annotées)
3. Rapport technique (choix d'architecture, résultats d'évaluation, limites identifiées)
4. Démonstration fonctionnelle (CLI ou petite interface) montrant une requête avec claims annotés
5. Support de présentation synthétique (pour entretiens ou candidature PFE)

---

## 8. Planning indicatif

| Phase | Contenu | Durée estimée |
|---|---|---|
| 1 | Conception détaillée + choix techniques (base vectorielle, format de claims, corpus) | 1–2 jours |
| 2 | Pipeline d'ingestion + indexation | 1–2 jours |
| 3 | Agent : génération + décomposition en claims | 2–3 jours |
| 4 | Module de vérification + verdicts | 2–3 jours |
| 5 | Jeu d'évaluation + mesure des métriques | 2 jours |
| 6 | Interface minimale + rapport + finalisation | 2 jours |

**Durée totale estimée : ~2 semaines** en travail régulier.

---

## 9. Risques identifiés

| Risque | Impact | Mitigation |
|---|---|---|
| Corpus trop simple → pas de vraies contradictions à détecter | Évaluation peu convaincante | Injecter des contradictions synthétiques volontairement |
| Décomposition en claims trop grossière ou trop fine | Verdicts peu fiables | Itérer sur le prompt de décomposition avec des exemples de calibration |
| Dérive de scope (vouloir tout couvrir) | Dépassement du temps imparti | Respecter strictement le périmètre défini en section 2.2 |
| Coût API élevé si corpus/tests mal maîtrisés | Blocage budgétaire | Limiter le corpus, mettre en cache les embeddings, utiliser un modèle économique pour les étapes intermédiaires |

---

## 10. Prochaines étapes

- Valider le choix du corpus (domaine et papiers spécifiques)
- Choisir la stack technique définitive (base vectorielle, format d'embedding)
- Démarrer par un prototype minimal end-to-end (une question, un corpus de 2-3 papiers) avant d'élargir
