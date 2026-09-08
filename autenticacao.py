"""
Módulo de autenticação.

Protege o acesso ao painel com uma senha única. A senha em texto puro nunca
fica salva no código — apenas o seu hash SHA-256 é comparado.

Para trocar a senha, gere um novo hash com o comando abaixo e substitua o
valor de HASH_SENHA_VALIDA:

    python -c "import hashlib; print(hashlib.sha256(b'NOVA_SENHA').hexdigest())"
"""
import hashlib
import secrets

import streamlit as st

# Senha padrão de fábrica: H2O2#2026  (troque assim que possível)
HASH_SENHA_VALIDA = "7e4852cb584beb0f9c701db218eca22125e7cae337f0813d3b5c1fdeadf33c00"


def _senha_valida(tentativa: str) -> bool:
    """Compara o hash da tentativa com o hash salvo, sem expor a senha real."""
    hash_tentativa = hashlib.sha256(tentativa.encode("utf-8")).hexdigest()
    return secrets.compare_digest(hash_tentativa, HASH_SENHA_VALIDA)


def exigir_login():
    """Mostra a tela de login e interrompe o app até a senha correta ser informada."""
    if "autenticado" not in st.session_state:
        st.session_state.autenticado = False

    if st.session_state.autenticado:
        return  # já logado, segue para o resto do app

    _, col_central, _ = st.columns([1, 1.1, 1])
    with col_central:
        st.markdown('<div class="cartao-login">', unsafe_allow_html=True)
        st.markdown("Acesso Restrito")
        st.caption("Monitor do Misturador de Gás · informe a senha para continuar")

        with st.form("form_login"):
            senha = st.text_input("Senha de acesso", type="password")
            entrar = st.form_submit_button("Entrar", use_container_width=True, type="primary")

        if entrar:
            if _senha_valida(senha):
                st.session_state.autenticado = True
                st.rerun()
            else:
                st.error("Senha incorreta. Tente novamente.")
        st.markdown("</div>", unsafe_allow_html=True)

    st.stop()  # impede que o restante do app.py seja executado sem login
