import fastapi 


app = fastapi.FastAPI()

@app.get("/")
def read_root():
    return {"message": "Hello, World!"}

def step1():
    return "Step 1"


def step2():
    return "Step 2"


def step3():
    return "Step 3"

def step4():
    return "Step 4"

def step5():
    return "Step 5"

@app.get("/run_pipeline")
def read_pipeline():
    step1()
    step2()
    step3()
    step4()
    step5()
    return "Pipeline run complete"