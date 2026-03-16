import os
import subprocess
import sys
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

# ==============================================================================
# 1. ENGENHARIA DE DEPENDÊNCIAS (Auto-Setup)
# ==============================================================================
from flask import Flask, render_template_string, request, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
import google.generativeai as genai
from pypdf import PdfReader
from docx import Document
import pandas as pd
import requests

# ==============================================================================
# 2. CONFIGURAÇÃO DO SERVIDOR E BANCO DE DATA
# ==============================================================================
app = Flask(__name__)
# No Coolify, o volume persistente deve ser mapeado para /app/data
DB_PATH = '/app/data/fabriccio_logis_v1.db'
if not os.path.exists('/app/data'):
    os.makedirs('/app/data', exist_ok=True)

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'fabriccio-logis-ultra-secret'
db = SQLAlchemy(app)

# Modelo para persistência de configurações globais
class AppSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True)
    value = db.Column(db.Text)

with app.app_context():
    db.create_all()

# ==============================================================================
# 3. UTILITÁRIOS DE EXTRAÇÃO DE ARQUIVOS
# ==============================================================================
def extract_text_from_file(file):
    """Extrai texto de PDF, DOCX, XLSX e TXT com tratamento de erros."""
    filename = file.filename.lower()
    content = ""
    try:
        if filename.endswith('.pdf'):
            reader = PdfReader(file)
            for page in reader.pages:
                content += page.extract_text() or ""
        elif filename.endswith('.docx'):
            doc = Document(file)
            for para in doc.paragraphs:
                content += para.text + "\n"
        elif filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(file)
            content = df.to_string()
        elif filename.endswith('.txt'):
            content = file.read().decode('utf-8')
    except Exception as e:
        logging.error(f"Erro ao ler arquivo {filename}: {e}")
        return f"\n[Erro no arquivo {filename}]\n"
    return content

# ==============================================================================
# 4. FRONTEND - TEMPLATE MONOLÍTICO (UI/UX DASHBOARD)
# ==============================================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="it" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Fabriccio-Logis v1 | Enterprise</title>
    <!-- Frameworks Modernos -->
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/sortablejs@1.15.0/Sortable.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    
    <style>
        :root { --primary: #6366f1; --bg-dark: #020617; }
        body { font-family: 'Plus Jakarta Sans', sans-serif; background: var(--bg-dark); color: #f8fafc; scroll-behavior: smooth; }
        .glass { background: rgba(15, 23, 42, 0.8); backdrop-filter: blur(16px); border: 1px solid rgba(51, 65, 85, 0.5); }
        .card-route { border-left: 5px solid #1e293b; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
        .card-route:hover { border-left-color: var(--primary); background: rgba(30, 41, 59, 0.7); transform: translateX(5px); }
        .card-route.is-post { border-left-color: #f59e0b; }
        .card-route.is-pickup { border-left-color: #10b981; }
        .loader { width: 24px; height: 24px; border: 3px solid #FFF; border-bottom-color: transparent; border-radius: 50%; display: inline-block; animation: rotation 1s linear infinite; }
        @keyframes rotation { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        @media print { .no-print { display: none !important; } .print-only { display: block !important; color: black; background: white; } }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-thumb { background: #334155; border-radius: 10px; }
    </style>
</head>
<body class="p-4 md:p-8 min-h-screen">

    <div class="max-w-7xl mx-auto">
        <!-- Header Section -->
        <header class="flex flex-col md:flex-row justify-between items-center mb-10 gap-6 no-print">
            <div class="flex items-center gap-4">
                <div class="bg-indigo-600 p-3 rounded-2xl shadow-lg shadow-indigo-500/20">
                    <svg class="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 20l-5.447-2.724A2 2 0 013 15.382V6.618a2 2 0 011.106-1.789L9 2m0 18l6-3m-6 3V7m6 10l4.553 2.276A2 2 0 0021 17.447V8.618a2 2 0 00-1.106-1.789L15 4m0 13V4m0 0L9 7"></path></svg>
                </div>
                <div>
                    <h1 class="text-4xl font-black tracking-tighter text-white">Fabriccio-Logis <span class="text-indigo-500">v1</span></h1>
                    <p id="txt_tagline" class="text-slate-500 text-sm font-medium italic"></p>
                </div>
            </div>
            <div class="flex gap-2 glass p-1.5 rounded-2xl shadow-xl">
                <button onclick="setLang('it')" class="lang-btn px-4 py-1.5 rounded-xl text-xs font-bold transition">IT</button>
                <button onclick="setLang('pt')" class="lang-btn px-4 py-1.5 rounded-xl text-xs font-bold transition">PT</button>
                <button onclick="setLang('en')" class="lang-btn px-4 py-1.5 rounded-xl text-xs font-bold transition">EN</button>
            </div>
        </header>

        <div class="grid grid-cols-1 lg:grid-cols-12 gap-8 no-print">
            
            <!-- Sidebar: Configurações Persistentes -->
            <aside class="lg:col-span-4 space-y-6">
                <div class="glass p-8 rounded-[2.5rem] space-y-5 shadow-2xl border-indigo-500/10">
                    <h3 class="text-lg font-bold flex items-center gap-2 text-indigo-400">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4"></path></svg>
                        <span id="txt_params"></span>
                    </h3>
                    
                    <div class="space-y-4">
                        <div>
                            <label class="text-[10px] text-slate-500 uppercase font-black tracking-widest mb-1 block">Partenza</label>
                            <input type="text" id="start_addr" oninput="persist()" class="w-full bg-slate-900/50 border border-slate-700 rounded-2xl p-4 text-sm focus:border-indigo-500 outline-none transition" placeholder="Indirizzo Casa/Ufficio">
                        </div>
                        <div>
                            <label class="text-[10px] text-slate-500 uppercase font-black tracking-widest mb-1 block">Agenzia di Riferimento</label>
                            <input type="text" id="post_addr" oninput="persist()" class="w-full bg-slate-900/50 border border-slate-700 rounded-2xl p-4 text-sm focus:border-indigo-500 outline-none transition" placeholder="DHL, Poste, etc...">
                        </div>
                    </div>

                    <div class="grid grid-cols-2 gap-4">
                        <div>
                            <label class="text-[10px] text-slate-500 uppercase font-black mb-1 block" id="txt_dep_time"></label>
                            <input type="time" id="departure_time" oninput="persist()" class="w-full bg-slate-900 border border-slate-700 p-3 rounded-2xl text-sm outline-none focus:border-indigo-500">
                        </div>
                        <div>
                            <label class="text-[10px] text-slate-500 uppercase font-black mb-1 block" id="txt_stop_time"></label>
                            <input type="number" id="avg_stop_time" oninput="persist()" class="w-full bg-slate-900 border border-slate-700 p-3 rounded-2xl text-sm outline-none focus:border-indigo-500">
                        </div>
                    </div>

                    <div class="space-y-3 pt-2">
                        <label class="flex items-center gap-3 cursor-pointer group">
                            <input type="checkbox" id="post_priority" onchange="persist()" class="w-5 h-5 rounded-lg accent-indigo-500">
                            <span class="text-xs text-slate-400 group-hover:text-indigo-400 transition" id="txt_post_prio"></span>
                        </label>
                        <label class="flex items-center gap-3 cursor-pointer group">
                            <input type="checkbox" id="return_home" onchange="persist()" class="w-5 h-5 rounded-lg accent-blue-500">
                            <span class="text-xs text-slate-400 group-hover:text-blue-400 transition" id="txt_return"></span>
                        </label>
                    </div>

                    <div class="pt-6 border-t border-slate-800 space-y-4">
                        <div>
                            <label class="text-[10px] text-slate-500 uppercase font-bold block mb-2">IA Engine</label>
                            <select id="ai_backend" onchange="persist()" class="w-full bg-slate-900 border border-slate-700 p-4 rounded-2xl text-sm outline-none">
                                <option value="gemini">Google Gemini Flash (Latest)</option>
                                <option value="ollama">Ollama (Local)</option>
                            </select>
                        </div>
                        
                        <div id="gemini_box" class="space-y-2">
                            <label class="text-[10px] text-slate-500 uppercase font-bold">API Key</label>
                            <input type="password" id="api_key" oninput="persist()" class="w-full bg-slate-950 border border-slate-700 p-4 rounded-2xl text-sm focus:border-indigo-500 outline-none" placeholder="Paste your Key here">
                            <a href="https://aistudio.google.com/app/apikey" target="_blank" class="text-[10px] text-indigo-400 underline flex items-center gap-1">Obtenha sua Chave Gemini <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg></a>
                        </div>

                        <div id="ollama_box" class="hidden space-y-2">
                            <label class="text-[10px] text-slate-500 uppercase font-bold">Model Name</label>
                            <input type="text" id="ollama_model" oninput="persist()" placeholder="ex: llama3" class="w-full bg-slate-950 border border-slate-700 p-4 rounded-2xl text-sm outline-none">
                            <a href="https://ollama.com/" target="_blank" class="text-[10px] text-indigo-400 underline flex items-center gap-1">Baixe o Ollama aqui <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg></a>
                        </div>
                    </div>
                </div>
            </aside>

            <!-- Main Panel: Entrada e Resultados -->
            <main class="lg:col-span-8 space-y-6">
                <!-- Data Entry Card -->
                <div class="glass p-8 rounded-[2.5rem] border-t-4 border-indigo-600 shadow-2xl relative overflow-hidden">
                    <textarea id="manual_text" oninput="persist()" class="w-full h-48 bg-slate-950/30 border border-slate-800 rounded-3xl p-6 text-sm outline-none focus:border-indigo-500 mb-6 transition resize-none" placeholder="Endereços, OS, Notas..."></textarea>
                    
                    <!-- File Management -->
                    <div id="file_list" class="flex flex-wrap gap-2 mb-6"></div>

                    <div class="flex flex-col md:flex-row gap-4">
                        <button onclick="document.getElementById('file_input').click()" class="flex-1 bg-slate-800 hover:bg-slate-700 py-5 rounded-[1.5rem] font-bold transition flex items-center justify-center gap-3">
                            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"></path></svg>
                            <span id="txt_attach"></span>
                            <input type="file" id="file_input" multiple class="hidden" onchange="handleFiles(this.files)">
                        </button>
                        <button onclick="process()" id="btn_run" class="flex-[2] bg-gradient-to-r from-blue-600 to-indigo-600 hover:scale-[1.02] py-5 rounded-[1.5rem] font-black text-white shadow-xl shadow-indigo-500/20 uppercase tracking-[0.2em] transition">
                            <span id="run_spinner" class="loader hidden mr-2"></span>
                            <span id="txt_btn_run_text"></span>
                        </button>
                    </div>

                    <div class="mt-8 flex flex-wrap gap-6 text-[10px] text-slate-500 uppercase font-black opacity-50 border-t border-slate-800 pt-6">
                        <span class="flex items-center gap-1"><b class="text-indigo-400 text-sm">#</b> Priorità</span>
                        <span class="flex items-center gap-1"><b class="text-amber-500 text-sm">*</b> Corriere</span>
                        <span class="flex items-center gap-1"><b class="text-indigo-400 italic">🤖 IA</b> Auto-Detect OS/Client</span>
                    </div>
                </div>

                <!-- Results Section -->
                <div id="results_area" class="hidden space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-700">
                    <div class="flex justify-between items-end px-4">
                        <h2 class="text-3xl font-black tracking-tight" id="txt_itinerary"></h2>
                        <div id="total_time_badge" class="bg-indigo-500/10 text-indigo-400 px-6 py-3 rounded-2xl text-xs font-black border border-indigo-500/20 shadow-lg uppercase"></div>
                    </div>
                    
                    <div id="route_list" class="space-y-4">
                        <!-- Card dynamic injection -->
                    </div>

                    <!-- Action Grid -->
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-4 pt-8">
                        <button onclick="openMaps()" class="bg-emerald-600 hover:bg-emerald-700 py-5 rounded-[1.5rem] font-bold text-xs uppercase transition shadow-xl shadow-emerald-900/20 flex items-center justify-center gap-2">
                            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z" clip-rule="evenodd"></path></svg> Google Maps
                        </button>
                        <button onclick="window.print()" class="bg-slate-700 hover:bg-slate-600 py-5 rounded-[1.5rem] font-bold text-xs uppercase transition shadow-xl flex items-center justify-center gap-2">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"></path></svg> Imprimir
                        </button>
                        <button onclick="sharePDF()" class="bg-indigo-600 hover:bg-indigo-700 py-5 rounded-[1.5rem] font-bold text-xs uppercase transition shadow-xl shadow-indigo-900/20 flex items-center justify-center gap-2">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z"></path></svg> Share PDF
                        </button>
                    </div>
                </div>
            </main>
        </div>

        <!-- Print Output Area (Formatted for Paper) -->
        <div class="print-only hidden p-10 text-black bg-white">
            <h1 class="text-3xl font-black mb-8 border-b-4 border-black pb-4 uppercase">Itinerario Fabriccio-Logis</h1>
            <div id="print_content" class="space-y-6"></div>
            <div id="print_master_link" class="mt-12 pt-8 border-t-2 border-dashed border-gray-400 text-xs break-all text-blue-800 font-mono"></div>
        </div>
    </div>

    <!-- Edit Modal (SaaS Grade) -->
    <div id="edit_modal" class="fixed inset-0 bg-slate-950/90 backdrop-blur-xl hidden flex items-center justify-center z-[100] p-6">
        <div class="glass max-w-2xl w-full p-10 rounded-[3rem] shadow-2xl space-y-6 border border-white/10">
            <h3 class="text-2xl font-black tracking-tight flex items-center gap-2">
                <div class="w-2 h-8 bg-indigo-500 rounded-full"></div> Modifica Fermata
            </h3>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div class="md:col-span-2">
                    <label class="text-[10px] uppercase font-bold text-slate-500 mb-1 block">Indirizzo</label>
                    <input type="text" id="edit_addr" class="w-full bg-slate-900/50 border border-slate-700 p-4 rounded-2xl outline-none focus:border-indigo-500">
                </div>
                <div>
                    <label class="text-[10px] uppercase font-bold text-slate-500 mb-1 block">Empresa / Ditta</label>
                    <input type="text" id="edit_company" class="w-full bg-slate-900/50 border border-slate-700 p-4 rounded-2xl outline-none focus:border-indigo-500">
                </div>
                <div>
                    <label class="text-[10px] uppercase font-bold text-slate-500 mb-1 block">Nome Cliente</label>
                    <input type="text" id="edit_client" class="w-full bg-slate-900/50 border border-slate-700 p-4 rounded-2xl outline-none focus:border-indigo-500">
                </div>
                <div>
                    <label class="text-[10px] uppercase font-bold text-slate-500 mb-1 block">Ordem de Serviço (OS)</label>
                    <input type="text" id="edit_os" class="w-full bg-slate-900/50 border border-slate-700 p-4 rounded-2xl outline-none focus:border-indigo-500">
                </div>
                <div>
                    <label class="text-[10px] uppercase font-bold text-slate-500 mb-1 block">Tempo Parada (min)</label>
                    <input type="number" id="edit_duration" class="w-full bg-slate-900/50 border border-slate-700 p-4 rounded-2xl outline-none focus:border-indigo-500">
                </div>
                <div class="md:col-span-2">
                    <label class="text-[10px] uppercase font-bold text-slate-500 mb-1 block">Note / Istruzioni</label>
                    <textarea id="edit_notes" class="w-full bg-slate-900/50 border border-slate-700 p-4 rounded-2xl h-24 outline-none resize-none focus:border-indigo-500"></textarea>
                </div>
            </div>
            <div class="flex gap-4 pt-6">
                <button onclick="closeEdit()" class="flex-1 py-4 bg-slate-800 rounded-2xl font-bold hover:bg-slate-700 transition">Chiudi</button>
                <button onclick="saveEdit()" class="flex-1 py-4 bg-indigo-600 rounded-2xl font-bold hover:bg-indigo-500 transition shadow-lg shadow-indigo-500/20">Salva Modifiche</button>
            </div>
        </div>
    </div>

    <script>
        // ==============================================================================
        // JAVASCRIPT MASTER LOGIC
        // ==============================================================================
        const i18n = {
            it: { tagline: "Ottimizzazione intelligente per la logistica quotidiana.", params: "Configurazione", dep_time: "Partenza", stop_time: "Min/Fermata", post_prio: "Corriere come 1ª tappa (Sempre)", return: "Ritorno al punto iniziale", attach: "ALLEGATI", run: "CALCOLA PERCORSO", itinerary: "Itinerario Ottimizzato" },
            pt: { tagline: "Otimização inteligente para a logística diária.", params: "Configuração", dep_time: "Partida", stop_time: "Min/Parada", post_prio: "Correio como 1ª etapa (Sempre)", return: "Voltar ao ponto inicial", attach: "ANEXAR ARQUIVOS", run: "OTIMIZAR AGORA", itinerary: "Itinerário Calculado" },
            en: { tagline: "Smart optimization for daily logistics.", params: "Settings", dep_time: "Departure", stop_time: "Min/Stop", post_prio: "Post Office 1st (Always)", return: "Return to home", attach: "ATTACH FILES", run: "OPTIMIZE NOW", itinerary: "Calculated Route" }
        };

        let state = {
            lang: localStorage.getItem('fb_lang_v1') || 'it',
            results: [],
            files: [],
            editIndex: -1
        };

        // UI Initialization
        function setLang(l) {
            state.lang = l; localStorage.setItem('fb_lang_v1', l);
            const d = i18n[l];
            document.getElementById('txt_tagline').innerText = d.tagline;
            document.getElementById('txt_params').innerText = d.params;
            document.getElementById('txt_dep_time').innerText = d.dep_time;
            document.getElementById('txt_stop_time').innerText = d.stop_time;
            document.getElementById('txt_post_prio').innerText = d.post_prio;
            document.getElementById('txt_return').innerText = d.return;
            document.getElementById('txt_attach').innerText = d.attach;
            document.getElementById('txt_btn_run_text').innerText = d.run;
            document.getElementById('txt_itinerary').innerText = d.itinerary;
            
            document.querySelectorAll('.lang-btn').forEach(btn => {
                btn.classList.toggle('bg-indigo-600', btn.innerText.toLowerCase() === l);
                btn.classList.toggle('text-white', btn.innerText.toLowerCase() === l);
                btn.classList.toggle('text-slate-500', btn.innerText.toLowerCase() !== l);
            });
        }

        // File Management
        function handleFiles(fileList) {
            for(let f of fileList) state.files.push(f);
            renderFiles();
        }

        function removeFile(index) {
            state.files.splice(index, 1);
            renderFiles();
        }

        function renderFiles() {
            const list = document.getElementById('file_list');
            list.innerHTML = '';
            state.files.forEach((f, i) => {
                list.innerHTML += `
                    <div class="bg-indigo-500/10 border border-indigo-500/20 text-indigo-300 px-4 py-2 rounded-xl text-[10px] flex items-center gap-3 animate-in fade-in zoom-in duration-300">
                        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"></path></svg>
                        ${f.name} 
                        <b class="cursor-pointer hover:text-red-400 p-1 bg-white/5 rounded-md transition" onclick="removeFile(${i})">✕</b>
                    </div>`;
            });
        }

        // State Management (Persistence)
        function persist() {
            const d = {
                start: document.getElementById('start_addr').value,
                post: document.getElementById('post_addr').value,
                dep: document.getElementById('departure_time').value,
                stop: document.getElementById('avg_stop_time').value,
                key: document.getElementById('api_key').value,
                ollama: document.getElementById('ollama_model').value,
                text: document.getElementById('manual_text').value,
                prio: document.getElementById('post_priority').checked,
                ret: document.getElementById('return_home').checked,
                ai: document.getElementById('ai_backend').value
            };
            localStorage.setItem('fb_data_v1', JSON.stringify(d));
            document.getElementById('gemini_box').classList.toggle('hidden', d.ai !== 'gemini');
            document.getElementById('ollama_box').classList.toggle('hidden', d.ai !== 'ollama');
        }

        function loadState() {
            const s = JSON.parse(localStorage.getItem('fb_data_v1') || '{}');
            document.getElementById('start_addr').value = s.start || '';
            document.getElementById('post_addr').value = s.post || '';
            document.getElementById('departure_time').value = s.dep || '08:00';
            document.getElementById('avg_stop_time').value = s.stop || '15';
            document.getElementById('api_key').value = s.key || '';
            document.getElementById('ollama_model').value = s.ollama || 'llama3';
            document.getElementById('manual_text').value = s.text || '';
            document.getElementById('post_priority').checked = s.prio || false;
            document.getElementById('return_home').checked = s.ret || false;
            document.getElementById('ai_backend').value = s.ai || 'gemini';
            persist();
        }

        // CORE PROCESSING
        async function process() {
            const btn = document.getElementById('btn_run');
            const spinner = document.getElementById('run_spinner');
            const btnText = document.getElementById('txt_btn_run_text');
            
            spinner.classList.remove('hidden');
            btnText.innerText = "IA ANALYZING...";
            btn.disabled = true;

            const fd = new FormData();
            fd.append('api_key', document.getElementById('api_key').value);
            fd.append('ollama_model', document.getElementById('ollama_model').value);
            fd.append('ai_backend', document.getElementById('ai_backend').value);
            fd.append('manual_text', document.getElementById('manual_text').value);
            fd.append('start_addr', document.getElementById('start_addr').value);
            fd.append('post_addr', document.getElementById('post_addr').value);
            fd.append('post_priority', document.getElementById('post_priority').checked);
            fd.append('return_home', document.getElementById('return_home').checked);
            state.files.forEach(f => fd.append('files', f));

            try {
                const res = await fetch('/api/optimize', { method: 'POST', body: fd });
                const data = await res.json();
                if(data.error) throw new Error(data.error);
                state.results = data.results;
                render();
            } catch(e) { 
                alert("Errore nell'elaborazione: " + e.message); 
            } finally {
                spinner.classList.add('hidden');
                btnText.innerText = i18n[state.lang].run;
                btn.disabled = false;
            }
        }

        function render() {
            const list = document.getElementById('route_list');
            const print = document.getElementById('print_content');
            document.getElementById('results_area').classList.remove('hidden');
            list.innerHTML = ''; print.innerHTML = '';
            
            let currentTime = new Date(`2024-01-01T${document.getElementById('departure_time').value}`);

            state.results.forEach((item, i) => {
                const arrival = new Date(currentTime.getTime() + (item.travel_time || 10) * 60000);
                const stopDuration = parseInt(item.stop_duration) || parseInt(document.getElementById('avg_stop_time').value) || 15;
                
                // Visual Card
                const card = document.createElement('div');
                card.className = `glass p-6 rounded-[2rem] card-route flex items-center gap-6 cursor-grab active:cursor-grabbing shadow-xl ${item.is_post ? 'is-post' : (item.is_pickup ? 'is-pickup' : '')}`;
                card.dataset.index = i;
                card.onclick = () => openEdit(i);
                card.innerHTML = `
                    <div class="text-3xl font-black text-slate-800 tracking-tighter">${String(i+1).padStart(2,'0')}</div>
                    <div class="flex-1 space-y-1">
                        <p class="font-bold text-lg text-white leading-tight">${item.addr}</p>
                        <div class="flex flex-wrap gap-x-4 gap-y-1 text-[10px] uppercase font-black text-slate-500 tracking-wider">
                            <span class="flex items-center gap-1"><i class="w-1.5 h-1.5 rounded-full bg-slate-700"></i> ${item.company || '--'}</span>
                            <span class="flex items-center gap-1"><i class="w-1.5 h-1.5 rounded-full bg-slate-700"></i> ${item.client || '--'}</span>
                            <span class="flex items-center gap-1"><i class="w-1.5 h-1.5 rounded-full bg-slate-700"></i> OS: ${item.os || '--'}</span>
                            <span class="text-indigo-400 flex items-center gap-1"><svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg> ARR: ${arrival.toTimeString().substring(0,5)}</span>
                        </div>
                    </div>
                    <div class="flex flex-col items-center gap-1">
                        <div class="text-3xl filter drop-shadow-md">${item.is_post ? '📮' : (item.is_pickup ? '📥' : '📦')}</div>
                        ${item.is_pickup ? '<span class="text-[8px] font-black text-emerald-500 uppercase tracking-widest">Ritiro</span>' : ''}
                    </div>
                `;
                list.appendChild(card);

                // Paper Template
                print.innerHTML += `
                    <div class="border-b-2 border-gray-200 pb-4">
                        <div class="flex justify-between items-start">
                            <p class="text-xl font-black">${i+1}. ${item.addr}</p>
                            <p class="font-bold text-gray-500">ARR: ${arrival.toTimeString().substring(0,5)}</p>
                        </div>
                        <div class="grid grid-cols-3 gap-4 text-sm mt-2 font-bold uppercase text-gray-700">
                            <p>Empresa: ${item.company || '--'}</p>
                            <p>Cliente: ${item.client || '--'}</p>
                            <p>OS: ${item.os || '--'}</p>
                        </div>
                        ${item.notes ? `<p class="text-sm mt-1 italic text-gray-600">Note: ${item.notes}</p>` : ''}
                        <div class="mt-2 flex gap-4 text-[10px] font-mono text-blue-600">
                            <a href="https://www.google.com/maps/search/${encodeURIComponent(item.addr)}">[Ver no Mapa Singular]</a>
                        </div>
                    </div>
                `;

                currentTime = new Date(arrival.getTime() + stopDuration * 60000);
            });

            document.getElementById('total_time_badge').innerText = `Finish Estimated: ${currentTime.toTimeString().substring(0,5)}`;
            document.getElementById('print_master_link').innerText = "FULL ROUTE URL: " + getMasterLink();

            new Sortable(list, { animation: 150, ghostClass: 'bg-indigo-500/10', onEnd: () => {
                const newOrder = [];
                document.querySelectorAll('#route_list > div').forEach(div => newOrder.push(state.results[div.dataset.index]));
                state.results = newOrder;
                render();
            }});
        }

        // Edit Modal Functions
        function openEdit(i) {
            state.editIndex = i;
            const r = state.results[i];
            document.getElementById('edit_addr').value = r.addr;
            document.getElementById('edit_company').value = r.company || '';
            document.getElementById('edit_client').value = r.client || '';
            document.getElementById('edit_os').value = r.os || '';
            document.getElementById('edit_notes').value = r.notes || '';
            document.getElementById('edit_duration').value = r.stop_duration || document.getElementById('avg_stop_time').value;
            document.getElementById('edit_modal').classList.remove('hidden');
        }
        function closeEdit() { document.getElementById('edit_modal').classList.add('hidden'); }
        function saveEdit() {
            const r = state.results[state.editIndex];
            r.addr = document.getElementById('edit_addr').value;
            r.company = document.getElementById('edit_company').value;
            r.client = document.getElementById('edit_client').value;
            r.os = document.getElementById('edit_os').value;
            r.notes = document.getElementById('edit_notes').value;
            r.stop_duration = document.getElementById('edit_duration').value;
            closeEdit(); render();
        }

        // Export Functions
        function getMasterLink() {
            const start = document.getElementById('start_addr').value;
            let url = `https://www.google.com/maps/dir/${encodeURIComponent(start)}/`;
            state.results.forEach(r => url += encodeURIComponent(r.addr) + "/");
            if(document.getElementById('return_home').checked) url += encodeURIComponent(start);
            return url;
        }

        function openMaps() { window.open(getMasterLink(), '_blank'); }

        async function sharePDF() {
            const { jsPDF } = window.jspdf;
            const doc = new jsPDF();
            doc.setFontSize(22); doc.text("Fabriccio-Logis V1 Itinerary", 20, 25);
            doc.setFontSize(10); doc.setTextColor(100);
            doc.text("Gerado em: " + new Date().toLocaleString(), 20, 32);
            
            let y = 50;
            state.results.forEach((r, i) => {
                doc.setFontSize(12); doc.setTextColor(0); doc.setFont("helvetica", "bold");
                doc.text(`${i+1}. ${r.addr}`, 20, y);
                y += 6;
                doc.setFontSize(9); doc.setFont("helvetica", "normal"); doc.setTextColor(80);
                doc.text(`Empresa: ${r.company || '--'} | OS: ${r.os || '--'} | Cliente: ${r.client || '--'}`, 20, y);
                y += 10;
                if(y > 270) { doc.addPage(); y = 20; }
            });

            const pdfBlob = doc.output('blob');
            const file = new File([pdfBlob], "rota-fabriccio-logis.pdf", { type: "application/pdf" });
            if(navigator.share) await navigator.share({ files: [file], title: 'Itinerario Logístico - Fabriccio-Logis' });
            else doc.save("itinerario.pdf");
        }

        // Run
        loadState(); setLang(state.lang);
    </script>
</body>
</html>
"""

# ==============================================================================
# 5. CORE LOGIC (AI & ROUTES)
# ==============================================================================
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/optimize', methods=['POST'])
def optimize():
    try:
        # 1. Coleta de Parâmetros do Frontend
        backend = request.form.get('ai_backend')
        api_key = request.form.get('api_key')
        ollama_model = request.form.get('ollama_model', 'gemma:2b') # Padrão gemma:2b
        manual_text = request.form.get('manual_text', '')
        start_addr = request.form.get('start_addr', '')
        post_addr = request.form.get('post_addr', '')
        post_priority = request.form.get('post_priority') == 'true'
        return_home = request.form.get('return_home') == 'true'
        
        # 2. Extração de Texto de Arquivos Enviados
        files = request.files.getlist('files')
        combined_context = f"TEXTO MANUAL:\n{manual_text}\n\n"
        for f in files:
            if f.filename:
                combined_context += f"--- CONTEÚDO DO ARQUIVO: {f.filename} ---\n"
                combined_context += extract_text_from_file(f) + "\n"

        # 3. Engenharia de Prompt (O "Cérebro" da Logística)
        prompt = f"""
        SISTEMA DE LOGÍSTICA FABRICCIO-LOGIS V1.
        
        OBJETIVO: Criar uma lista JSON de paradas otimizadas.
        
        PARÂMETROS DE ROTA:
        - INÍCIO: {start_addr}
        - AGÊNCIA DE CORREIO/COLETA: {post_addr}
        - PRIORIDADE DO CORREIO (1ª PARADA): {'SIM' if post_priority else 'NÃO'}
        - VOLTAR PARA CASA NO FIM: {'SIM' if return_home else 'NÃO'}

        REGRAS:
        1. Extraia Endereço, Empresa, Cliente e OS.
        2. Se 'is_pickup' for true, significa que o motorista deve RETIRAR algo na agência ({post_addr}) para levar a esse cliente.
        3. Se PRIORIDADE DO CORREIO for SIM, a parada '{post_addr}' deve ser o índice 0.
        4. Organize por proximidade geográfica lógica.

        SAÍDA OBRIGATÓRIA (JSON PURO):
        [
          {{
            "addr": "Rua Exemplo, 123",
            "company": "Nome",
            "client": "Nome",
            "os": "12345",
            "notes": "...",
            "is_post": false,
            "is_pickup": false,
            "travel_time": 15,
            "stop_duration": 15
          }}
        ]
        """

        json_text = ""

        # --- LÓGICA GOOGLE GEMINI ---
        if backend == 'gemini':
            if not api_key:
                return jsonify({"error": "API Key do Gemini não fornecida"}), 400
            
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt + "\n\nCONTEXTO PARA ANALISAR:\n" + combined_context)
            json_text = response.text

        # --- LÓGICA OLLAMA (LOCAL NO UBUNTU/COOLIFY) ---
        else:
            # Pega a URL do Ollama via variável de ambiente (definida no Docker Compose)
            # Se rodando no Coolify, OLLAMA_URL deve ser http://ollama_service:11434
            OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://ollama_service:11434')
            
            payload = {
                "model": ollama_model,
                "prompt": prompt + "\n\nTEXTO PARA ANALISE:\n" + combined_context,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_ctx": 4096 # Garante que ele lembre de todos os endereços
                }
            }

            try:
                # Timeout de 300 segundos (5 minutos) para CPUs lentas
                res = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=300)
                res.raise_for_status()
                json_text = res.json().get('response', '')
            except requests.exceptions.ConnectionError:
                return jsonify({"error": "Não foi possível conectar ao Ollama. Verifique se o container ollama_service está rodando."}), 503
            except requests.exceptions.Timeout:
                return jsonify({"error": "O Ollama demorou muito para processar (Timeout). Tente enviar menos endereços por vez."}), 504

        # 4. Limpeza e Parsing do JSON (Tratamento de erro robusto)
        try:
            # Remove blocos de markdown se a IA colocar (ex: ```json ... ```)
            clean_json = json_text.strip()
            if "```json" in clean_json:
                clean_json = clean_json.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_json:
                clean_json = clean_json.split("```")[1].split("```")[0].strip()
            
            data = json.loads(clean_json)
            return jsonify({"results": data})

        except Exception as e:
            logging.error(f"Erro ao parsear JSON da IA: {json_text}")
            return jsonify({
                "error": "A IA gerou uma resposta em formato inválido. Tente novamente.",
                "raw_details": str(e)
            }), 500

    except Exception as e:
        logging.error(f"Erro Crítico na API: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Configuração de Logs para Produção
    logging.basicConfig(level=logging.INFO)
    app.run(host='0.0.0.0', port=5000)
