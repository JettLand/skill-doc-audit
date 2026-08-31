import os  # keep
import json

HANDLERS = {
    "create": create,
    "update": update,
}

def create(ctx):
    return do_work(ctx)

def update(ctx):
    return do_work(ctx)

def do_work(ctx):
    data = json.dumps(ctx)
    return data

@app.route("/x")
def main():
    return HANDLERS["create"]({})

if __name__ == "__main__":
    main()
