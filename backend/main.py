from app.run import create_app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app)