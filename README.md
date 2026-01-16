This is a filestorage system for image/video storage and handling. It provides a web and desktop viewing and editing experience.

We provide an interactive cropping and image labelling pipeline. Furthermore, we use the value `labelplus` to specify any secondary/missed labels, i.e. two people in a photo.

<h2>Instructions</h2>  
Database set-up

```
setup.py
```  

Install `uv` and all dependencies in `pyproject.toml`.

Backend set-up and database population
```
cd backend
uv run setup.py
uv run manage.py setup
```

Frontend set-up
```
cd ../frontend`
npm install
```
Modify the next library
- https://github.com/vercel/next.js/pull/78566
- next/dist/server/lib/router-utils/proxy-request.js
- Line 36, add `secure: false,` to `HttpProxy`


<h2>Running application</h2>
Web backend

```
cd backend
uv run manage.py rs
```

Testing
```
cd backend
uv run -m coverage run manage.py test api
```

Frontend test coverage
```
cd frontend
npm run test:coverage
```

Desktop GUI
```
cd backend
uv run manage.py tkservice
```

Shell
```
cd backend
uv run manage.py shell_plus
```

Web frontend
```
cd frontend
npm run dev -- -p 3001
```
