import os

# Define the project structure and content
project_structure = {
    "CodeSentinel": {
        "batch-processor-service": {
            "go.mod": """module batch-processor-service

go 1.20

require (
    github.com/google/uuid v1.3.0
    github.com/labstack/echo/v4 v4.10.2
)""",
            "main.go": """package main

import (
    "net/http"
    "sync"
    "github.com/google/uuid"
    "github.com/labstack/echo/v4"
)

var (
    tasks = make(map[string]string)
    mutex = &sync.Mutex{}
)

func createTask(c echo.Context) error {
    id := uuid.New().String()
    mutex.Lock()
    tasks[id] = "pending"
    mutex.Unlock()
    return c.JSON(http.StatusOK, map[string]string{
        "task_id": id,
        "status":  "pending",
    })
}

func getTaskStatus(c echo.Context) error {
    id := c.Param("id")
    mutex.Lock()
    status, exists := tasks[id]
    mutex.Unlock()
    if !exists {
        return c.JSON(http.StatusNotFound, map[string]string{"error": "Task not found"})
    }
    return c.JSON(http.StatusOK, map[string]string{
        "task_id": id,
        "status":  status,
    })
}

func main() {
    e := echo.New()
    e.POST("/task", createTask)
    e.GET("/task/:id", getTaskStatus)
    e.Logger.Fatal(e.Start(":8081"))
}
"""
        },

        "code-scanner-service": {
            "Cargo.toml": """[package]
name = "code-scanner-service"
version = "0.1.0"
edition = "2021"

[dependencies]
actix-web = "4"
actix-multipart = "0.4"
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
serde_yaml = "0.9"
futures-util = "0.3"
""",
            "src/main.rs": """use actix_multipart::Multipart;
use actix_web::{web, App, HttpResponse, HttpServer, Responder};
use futures_util::StreamExt;
use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Serialize)]
struct Finding {
    path: String,
    method: String,
    issue: String,
}

async fn scan_openapi(mut payload: Multipart) -> impl Responder {
    let mut data = Vec::new();

    while let Some(mut field) = payload.next().await {
        while let Some(chunk) = field.next().await {
            let bytes = chunk.unwrap();
            data.extend_from_slice(&bytes);
        }
    }

    let openapi_spec: Value = match serde_yaml::from_slice(&data)
        .or_else(|_| serde_json::from_slice(&data))
    {
        Ok(spec) => spec,
        Err(_) => {
            return HttpResponse::BadRequest().body("Invalid OpenAPI spec format");
        }
    };

    let mut findings: Vec<Finding> = Vec::new();

    if let Some(paths) = openapi_spec.get("paths") {
        if let Some(paths_map) = paths.as_object() {
            for (path, methods) in paths_map {
                if let Some(methods_map) = methods.as_object() {
                    for (method, details) in methods_map {
                        let security = details.get("security");
                        if security.is_none() {
                            findings.push(Finding {
                                path: path.to_string(),
                                method: method.to_uppercase(),
                                issue: "No Authentication Required".to_string(),
                            });
                        }
                        if path.contains("{") && path.contains("}") {
                            findings.push(Finding {
                                path: path.to_string(),
                                method: method.to_uppercase(),
                                issue: "Potential IDOR Risk (parameter without control)".to_string(),
                            });
                        }
                    }
                }
            }
        }
    }

    HttpResponse::Ok().json(findings)
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    HttpServer::new(|| {
        App::new()
            .route("/scan", web::post().to(scan_openapi))
    })
    .bind(("0.0.0.0", 8080))?
    .run()
    .await
}
"""
        },        "llm-analyzer-service": {
            "requirements.txt": """fastapi
uvicorn""",
            "main.py": """from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
async def health_check():
    return {"status": "ok"}
"""
        },

        "dashboard-ui": {
            "package.json": """{
  "name": "dashboard-ui",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start"
  },
  "dependencies": {
    "next": "13.4.12",
    "react": "18.2.0",
    "react-dom": "18.2.0"
  }
}""",
            "pages/upload.js": """import { useState } from "react";

export default function Upload() {
  const [file, setFile] = useState(null);
  const [findings, setFindings] = useState([]);
  const [loading, setLoading] = useState(false);

  const handleFileChange = (e) => {
    setFile(e.target.files[0]);
  };

  const handleUpload = async () => {
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    setLoading(true);

    try {
      const response = await fetch("/scanner/scan", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) throw new Error("Upload failed");

      const data = await response.json();
      setFindings(data);
    } catch (error) {
      console.error(error);
      alert("Upload failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: "2rem" }}>
      <h1>Upload OpenAPI Spec for Scanning</h1>
      <input type="file" accept=".yaml,.yml,.json" onChange={handleFileChange} />
      <button onClick={handleUpload} disabled={!file || loading}>
        {loading ? "Scanning..." : "Upload and Scan"}
      </button>

      <hr />

      <h2>Findings:</h2>
      <ul>
        {findings.map((finding, idx) => (
          <li key={idx}>
            <strong>{finding.method}</strong> {finding.path} - {finding.issue}
          </li>
        ))}
      </ul>
    </div>
  );
}
"""
        },

        "deploy/k8s": {
            "scanner-deployment.yaml": """apiVersion: apps/v1
kind: Deployment
metadata:
  name: code-scanner
spec:
  replicas: 1
  selector:
    matchLabels:
      app: code-scanner
  template:
    metadata:
      labels:
        app: code-scanner
    spec:
      containers:
      - name: code-scanner
        image: code-scanner-service:latest
        ports:
        - containerPort: 8080
""",
            "scanner-service.yaml": """apiVersion: v1
kind: Service
metadata:
  name: code-scanner-service
spec:
  selector:
    app: code-scanner
  ports:
    - protocol: TCP
      port: 8080
      targetPort: 8080
"""
        },

        "helm/codesentinel": {
            "Chart.yaml": """apiVersion: v2
name: codesentinel
description: A Helm chart for CodeSentinel microservices
version: 0.1.0
""",
            "values.yaml": """replicaCount: 1

image:
  repository: codesentinel
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  port: 80
""",
            "templates/deployment.yaml": """apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "codesentinel.fullname" . }}
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels:
      app: {{ include "codesentinel.name" . }}
  template:
    metadata:
      labels:
        app: {{ include "codesentinel.name" . }}
    spec:
      containers:
        - name: {{ .Chart.Name }}
          image: "{{ .Values.image.repository }}:{{ .Chart.AppVersion }}"
          ports:
            - containerPort: 8080
"""
        }
    }
}        "scripts": {
            "setup-k3d.sh": """#!/bin/bash
# Setup a local K3d cluster for CodeSentinel
k3d cluster create codesentinel-cluster --port "8080:80@loadbalancer"
kubectl create namespace codesentinel
""",
            "build-push-all.sh": """#!/bin/bash
# Build docker images
docker build -t code-scanner-service:latest ./code-scanner-service
docker build -t batch-processor-service:latest ./batch-processor-service
docker build -t llm-analyzer-service:latest ./llm-analyzer-service
docker build -t dashboard-ui:latest ./dashboard-ui
""",
            "deploy-all.sh": """#!/bin/bash
# Deploy Kubernetes resources
kubectl apply -f deploy/k8s/
# Or use Helm
# helm install codesentinel helm/codesentinel/ --namespace codesentinel
"""
        },
        ".gitignore": """# Node
node_modules/
.next/

# Python
__pycache__/
*.pyc

# Rust
/target

# Go
/bin/
pkg/

# Docker
*.tar

# VSCode
.vscode/
""",
        ".dockerignore": """.git
node_modules
__pycache__
.vscode
*.tar
*.zip
""",
        "README.md": """# CodeSentinel

Microservice platform to scan APIs and codebases for authentication vulnerabilities using AI.

## Project Structure

- **code-scanner-service** (Rust)
- **batch-processor-service** (Go)
- **llm-analyzer-service** (Python)
- **dashboard-ui** (Next.js)

## Setup

1. Install Docker, K3d, kubectl
2. Run `scripts/setup-k3d.sh`
3. Build images with `scripts/build-push-all.sh`
4. Deploy with `scripts/deploy-all.sh`
5. Access dashboard on localhost:8080

## Services

- `/scanner/scan` for OpenAPI scanning
- `/task` and `/task/{id}` for batch processing
- `/health` endpoint for analyzer

"""
    }
}

def create_project(base_path, structure):
    for name, content in structure.items():
        path = os.path.join(base_path, name)
        if isinstance(content, dict):
            os.makedirs(path, exist_ok=True)
            create_project(path, content)
        else:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(content)

if __name__ == "__main__":
    create_project(".", project_structure)
    print("✅ CodeSentinel project generated successfully!")
