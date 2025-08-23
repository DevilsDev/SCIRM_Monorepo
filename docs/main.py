def define_env(env):
    env.variables["secrets"] = {"FIREBASE_PROJECT_ID": "scirm-dd5c3","DEPLOY_BRANCH": "firebase-hosting"}
    env.variables["github"] = env.conf.get("extra", {}).get("github", {})
    def pretty(val): return str(val).replace("_"," ").title()
    env.filters["pretty"] = pretty
