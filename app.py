"""Interface web de l'assistant RH (Streamlit).

Lancement : streamlit run app.py
"""
import sys
from pathlib import Path

import streamlit as st
import yaml

sys.path.insert(0, str(Path(__file__).parent / "src"))
from auth import authenticate, load_users  # noqa: E402
from monitoring import build_report, load_params, log_request, make_record, read_log  # noqa: E402
from rag import RAGAssistant  # noqa: E402

st.set_page_config(page_title="Assistant RH – TechMaroc", page_icon="📘", layout="wide")


@st.cache_resource            # le modèle d'embeddings et l'index ne sont chargés qu'une fois
def get_assistant():
    return RAGAssistant()


assistant = get_assistant()
monitoring = load_params()

# ---------- Connexion : le rôle vient du compte, l'utilisateur ne peut pas le choisir ----------
with open("params.yaml", encoding="utf-8") as f:
    auth_params = yaml.safe_load(f)["auth"]
st.session_state.setdefault("failed_attempts", 0)

if "user" not in st.session_state:
    st.title("Assistant RH – TechMaroc SA")
    if st.session_state["failed_attempts"] >= auth_params["max_attempts"]:
        st.error("Trop de tentatives. Contactez le support informatique.")
        st.stop()
    with st.form("login"):
        username = st.text_input("Identifiant")
        password = st.text_input("Mot de passe", type="password")
        submitted = st.form_submit_button("Se connecter", type="primary")
    if submitted:
        role = authenticate(username, password, load_users(auth_params["users_path"]))
        if role:
            st.session_state.update(user=username.strip().lower(), role=role, failed_attempts=0)
            st.rerun()
        st.session_state["failed_attempts"] += 1
        st.error("Identifiant ou mot de passe incorrect.")   # message volontairement non précis
    st.stop()

role = st.session_state["role"]
with st.sidebar:
    st.subheader("Session")
    st.write(f"Connecté : **{st.session_state['user']}**")
    st.caption(f"Rôle : {role} – documents visibles : {', '.join(assistant.params['roles'][role])}")
    if st.button("Se déconnecter"):
        for key in ("user", "role"):
            st.session_state.pop(key)
        st.rerun()

# ---------- Zone principale ----------
st.title("Assistant RH – TechMaroc SA")
st.caption("Réponses fondées uniquement sur les documents officiels, avec leurs sources. "
           "Assistant automatique : en cas de doute, contactez le service RH.")

question = st.text_input("Votre question", placeholder="Jusqu'à quand puis-je reporter mes congés ?")
if st.button("Envoyer", type="primary") and question.strip():
    model = assistant.params["llm_model"]
    try:
        with st.spinner("Recherche dans les documents…"):
            result = assistant.answer(question, role=role)
        log_request(make_record(question, role, model, result=result,
                                log_questions=monitoring["log_questions"]), monitoring["log_path"])
    except Exception as e:                       # erreur journalisée puis affichée proprement
        log_request(make_record(question, role, model, error=e), monitoring["log_path"])
        st.error(f"Le service est momentanément indisponible ({type(e).__name__}). Réessayez dans un instant.")
        st.stop()

    (st.warning if result["refused"] else st.success)(result["answer"])
    cols = st.columns(3)
    cols[0].caption("Refusé" if result["refused"] else "Répondu")
    cols[1].caption(f"Latence : {result['latency_ms']} ms")
    cols[2].caption(f"Tokens : {result['prompt_tokens']} + {result['completion_tokens']}")

    with st.expander("Sources récupérées"):
        st.dataframe(
            [{"similarité": s["similarity"], "chunk": s["chunk_id"], "accès": s["niveau_acces"],
              "statut": s["statut"], "section": s["section"] or f"page {s['page']}"} for s in result["sources"]],
            hide_index=True, use_container_width=True,
        )

# ---------- Monitoring (affiché en dernier : il inclut la requête qui vient d'être traitée) ----------
with st.sidebar:
    st.subheader("Monitoring")
    report = build_report(read_log(monitoring["log_path"]))
    if report["n_requests"]:
        st.metric("Requêtes", report["n_requests"])
        st.metric("Taux d'erreur", f"{report['error_rate']:.0%}")
        st.metric("Latence P95", f"{report['latency_p95_ms'] / 1000:.1f} s" if report["latency_p95_ms"] else "–")
        st.metric("Taux de refus", f"{report['refusal_rate']:.0%}" if report["refusal_rate"] is not None else "–")
        st.metric("Tokens moyens", report["tokens_mean"] or "–")
    else:
        st.caption("Aucune requête pour l'instant.")
