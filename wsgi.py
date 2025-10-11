from app import create_app

# usa tu factory con config por defecto "development"
app = create_app("development")

if __name__ == "__main__":
    # importante para Docker
    app.run(host="0.0.0.0", port=5000, debug=True)
