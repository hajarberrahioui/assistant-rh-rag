# Inventaire du corpus

| doc_id | Fichier | Format | Type | Version | Date | Accès | Statut | Origine | Rôle |
|---|---|---|---|---|---|---|---|---|---|
| CDT-001 | code_du_travail.pdf | PDF | loi | consolidée 2011 | 2011-10-26 | public | en_vigueur (traduction possiblement non à jour) | Officielle – adala.justice.gov.ma | Base légale |
| RI-001 | reglement_interieur.md | Markdown | reglement | 3.0 | 2026-01-15 | public | en_vigueur | Fictive | Horaires, absences, discipline |
| CONG-001 | politique_conges_v1.md | Markdown | politique | 1.0 | 2024-01-10 | public | **obsolete** | Fictive | Piège : ancienne version |
| CONG-002 | politique_conges_v2.md | Markdown | politique | 2.0 | 2026-01-01 | public | en_vigueur | Fictive | Version en vigueur, contredit la v1 |
| TT-001 | politique_teletravail.md | Markdown | politique | 1.2 | 2025-09-01 | public | en_vigueur | Fictive | Télétravail |
| FRAIS-001 | procedure_notes_de_frais.md | Markdown | procedure | 2.1 | 2025-11-15 | public | en_vigueur | Fictive | Notes de frais |
| ONB-001 | guide_onboarding.md | Markdown | guide | 1.4 | 2026-02-01 | public | en_vigueur | Fictive | Intégration |
| FAQ-001 | faq_rh.md | FAQ (Markdown Q/R) | faq | 2.0 | 2026-03-01 | public | en_vigueur | Fictive | Questions courantes |
| NOTE-014 | note_cafeteria.md | Markdown | note | 1.0 | 2026-10-05 | public | en_vigueur | Fictive | **Piège** : prompt injection — **en quarantaine, non indexé** (voir `data/processed/quarantaine.json`) |
| SAL-001 | grille_salariale.md | Markdown | grille | 2026 | 2026-01-01 | **rh** | en_vigueur | Fictive | Réservé (P2) |
| DISC-001 | procedure_disciplinaire.md | Markdown | procedure | 1.1 | 2025-06-01 | **rh** | en_vigueur | Fictive | Réservé (P2) |

## Contradictions volontaires entre CONG-001 (obsolète) et CONG-002 (en vigueur)
| Point | v1 (2024) | v2 (2026) |
|---|---|---|
| Jours de congés annuels | 18 | 22 (24 après 5 ans) |
| Report | jusqu'au 31/12 de l'année suivante | jusqu'au 31/03 |
| Demande | e-mail, 30 jours avant | portail RH, 15 jours (≥ 5 j) ou 5 jours (< 5 j) |
| Réponse du manager | 10 jours | 5 jours ouvrables |
| Mariage du salarié | 4 jours | 5 jours |
| Congé sans solde | non prévu | jusqu'à 3 mois après 2 ans d'ancienneté |

Comportement attendu : l'assistant s'appuie sur la **v2** et, si la v1 est récupérée, signale qu'elle est obsolète.

## Quarantaine
À l'ingestion, tout document contenant une instruction adressée à l'IA est écarté et listé dans `data/processed/quarantaine.json` pour relecture humaine. Actuellement : NOTE-014.

## Limites connues
- La traduction française du Code du travail date de 2011 ; certains articles ont pu être modifiés depuis.
- Les documents internes sont fictifs : ils ne décrivent aucune entreprise réelle.
