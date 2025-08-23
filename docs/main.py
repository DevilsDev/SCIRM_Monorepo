# docs/main.py
def define_env(env):
    """
    mkdocs-macros entrypoint. Provide safe defaults so templates never break.
    DO NOT put real secrets here.
    """
    env.variables["secrets"] = {
        "FIREBASE_PROJECT_ID": "scirm-dd5c3",
        "DEPLOY_BRANCH": "firebase-hosting",
    }
    # expose github config from mkdocs.yml -> extra.github (if present)
    env.variables["github"] = env.conf.get("extra", {}).get("github", {})

    # optional pretty filter
    def pretty(val):
        return str(val).replace("_", " ").title()
    env.filters["pretty"] = pretty
