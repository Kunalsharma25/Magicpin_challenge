from app import app

# Placeholder compose function for offline submission until composer module is built
def compose(category, merchant, trigger, customer=None):
    return {
        "body": "Placeholder message",
        "cta": "binary",
        "send_as": "vera",
        "suppression_key": trigger.suppression_key if hasattr(trigger, "suppression_key") else "key",
        "rationale": "Placeholder rationale"
    }

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
