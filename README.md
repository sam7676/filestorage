<h1>File Storage</h1>

This is a file storage system for image/video storage and handling. It provides a web and desktop viewing, managing and processing experience.

We provide an interactive cropping and image labelling pipeline. Furthermore, we use the value `labelplus` to specify any secondary/missed labels, e.g. a car and a lorry in the same photo.

<h2>Instructions</h2>  
Database set-up

```
setup.py
```  

Backend set-up and database population

Install `uv` and all dependencies in `pyproject.toml`.   
Install VLC media player.
```
cd backend
uv run setup.py
uv run manage.py setup
```
Set `READER_PATHS` in `.env` to one or more ingest directories separated by your OS path separator (Windows `;`, Linux/macOS `:`).

Frontend set-up
```
cd frontend
npm install
```
Modify the `Next.js` library to disable certificate verification, lets us run `https` locally.
- next/dist/server/lib/router-utils/proxy-request.js
- Line 36, add `secure: false,` to [`HttpProxy`](https://github.com/vercel/next.js/pull/78566/files#diff-1c32ef9038bd9006cb67b6af10b69a28e97279e750aa7885fd71d442427f0060R37)


<h2>Running application</h2>
Web backend

```
cd backend
uv run manage.py rs
```

Backend testing
```
cd backend
uv run python scripts/run_tests.py --coverage
```

Frontend testing
```
cd frontend
npm run test:coverage
```

Desktop GUI
```
cd backend
uv run manage.py qtservice 
```

Shell
```
cd backend
uv run manage.py shell_plus
```

Web frontend   
Runs on port 3000 by default, change with `-- -p [portNumber]`.
```
cd frontend
npm run dev
```
