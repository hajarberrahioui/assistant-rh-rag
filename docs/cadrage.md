# Cadrage du projet – Assistant RH (RAG)

## 1. Problème
TechMaroc SA (entreprise fictive, ~200 salariés, services informatiques) : le service RH reçoit en permanence les mêmes questions (congés, télétravail, notes de frais, intégration). Les réponses prennent du temps et ne sont pas toujours cohérentes.

L'assistant répond à ces questions **à partir des documents officiels**, **cite ses sources**, et **renvoie vers le service RH** lorsqu'il ne dispose pas d'informations suffisantes.

## 2. Utilisateurs
- **Employés** : accès aux documents publics.
- **RH / managers** : accès en plus aux documents restreints (extension P2).

## 3. Périmètre
| Dans le périmètre | Hors périmètre (refus ou redirection) |
|---|---|
| Congés, durée du travail, télétravail, notes de frais, onboarding, règlement intérieur, droits de base du Code du travail | Salaire d'une personne précise, situation personnelle (litige, licenciement individuel), conseil juridique, questions sans rapport avec les RH |

## 4. Conséquences d'une réponse incorrecte
Un employé prend des congés auxquels il n'a pas droit, une information confidentielle fuit, ou un conseil juridique erroné est donné.
→ Règles du système : **sources obligatoires**, **refus explicite**, **renvoi vers le service RH**.

## 5. Données et droits
- Code du travail marocain (loi n° 65-99), version française consolidée au 26/10/2011, publiée par le ministère de la Justice (adala.justice.gov.ma) : texte officiel public.
- Documents internes de TechMaroc SA : **fictifs**, rédigés pour le projet et déclarés comme tels.

## 6. Évaluation
Jeu d'environ 30 questions annotées (question, document attendu, réponse attendue) :
- ~20 questions dans le périmètre ;
- ~5 questions hors périmètre (refus attendu) ;
- ~5 pièges : contradiction congés v1/v2, question ambiguë, document contenant une instruction malveillante.

## 7. Indicateurs
Recall@5 (retrieval), fidélité de la réponse aux sources, taux de refus corrects, latence P95, tokens consommés par requête.
Les seuils des quality gates seront fixés **après une première mesure de référence (baseline)**.
