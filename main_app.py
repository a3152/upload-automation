import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog
import flickr_api
from flickr_api import Collection # Importar apenas o que é necessário
import os
import threading
import sys
import logging
import json
import time

# --- Configuração do Logger para ficheiro ---
# Isto irá criar um ficheiro de log com informação técnica detalhada para debugging.
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='flickr_uploader.log',
    filemode='w'
)

# --- Função para encontrar o diretório da aplicação ---
def get_app_path():
    """Retorna o diretório base da aplicação, seja script ou executável."""
    if getattr(sys, 'frozen', False):
        # Se estiver a correr como um executável (congelado pelo PyInstaller)
        return os.path.dirname(sys.executable)
    else:
        # Se estiver a correr como um script normal
        # Usar __file__ para garantir que funciona mesmo que o script seja chamado de outro diretório
        return os.path.dirname(os.path.abspath(__file__))

# --- Configurações da API ---
# Substitua pelas suas credenciais
CHAVE_API = "9521df685a2ece50adc0188f758fc23a"
SEGREDO_API = "2baba068929a80df"

# O ficheiro de token deve estar sempre junto ao executável/script
TOKEN_FILE = os.path.join(get_app_path(), 'oauth-token.txt')


class FlickrUploaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Flickr Multi-Album Uploader by Gemini")
        self.root.geometry("700x800") # Ajustado para a nova interface

        # Listas dinâmicas para os álbuns
        self.albums_data = []
        self.file_paths = []
        self.cover_photo_paths = []
        self.collection_comboboxes = []
        self.collections_list = []
        self.album_frames = []
        self.auth_handler = None # Variável para guardar o gestor de autenticação

        # Variáveis do temporizador
        self.timer_running = False
        self.start_time = 0

        logging.info("Aplicação iniciada.")
        logging.debug(f"A usar o ficheiro de token em: {TOKEN_FILE}")

        self.setup_widgets()
        self.log_message("Bem-vindo! A autenticar com o Flickr...")
        
        if self.authenticate_flickr():
            self.fetch_collections_thread()
        else:
            self.log_message("ERRO: Falha na autenticação. Verifique as suas chaves e o ficheiro 'oauth-token.txt'.")
            messagebox.showerror("Erro de Autenticação", "Não foi possível autenticar com o Flickr.")

    def setup_widgets(self):
        main_frame = tk.Frame(self.root, padx=10, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Frame superior para botões de controlo
        top_frame = tk.Frame(main_frame)
        top_frame.pack(fill=tk.X, pady=(0, 5))

        self.refresh_button = tk.Button(top_frame, text="Atualizar Lista de Coleções do Flickr", command=self.fetch_collections_thread)
        self.refresh_button.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # --- Criar a área de scroll para os álbuns ---
        scroll_container = tk.Frame(main_frame, bd=2, relief=tk.SUNKEN)
        scroll_container.pack(fill=tk.BOTH, expand=True, pady=5)

        canvas = tk.Canvas(scroll_container)
        scrollbar = ttk.Scrollbar(scroll_container, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas) # Frame onde os álbuns serão adicionados

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Botão para adicionar mais álbuns
        self.add_album_button = tk.Button(main_frame, text="Adicionar Novo Álbum +", command=self.add_album_form, bg="#007BFF", fg="white", font=('Helvetica', 10, 'bold'))
        self.add_album_button.pack(pady=10, fill=tk.X)
        
        # Iniciar com um formulário de álbum
        self.add_album_form()

        # Frame para o botão de upload e temporizador
        bottom_controls_frame = tk.Frame(main_frame)
        bottom_controls_frame.pack(pady=10, fill=tk.X)

        self.upload_button = tk.Button(bottom_controls_frame, text="Iniciar Upload de Todos os Álbuns", command=self.start_upload_thread, bg="#4CAF50", fg="white", font=('Helvetica', 12, 'bold'))
        self.upload_button.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5)

        self.timer_label = tk.Label(bottom_controls_frame, text="Tempo: 00:00:00", font=('Helvetica', 10, 'bold'), padx=10)
        self.timer_label.pack(side=tk.RIGHT)

        tk.Label(main_frame, text="Log de Progresso:", font=('Helvetica', 10, 'bold')).pack(anchor='w')
        self.log_area = scrolledtext.ScrolledText(main_frame, height=8, state='disabled', font=('Courier New', 9))
        self.log_area.pack(fill=tk.BOTH, expand=True)

    def add_album_form(self):
        index = len(self.albums_data)
        album_count = index + 1
        
        self.file_paths.append([])
        self.cover_photo_paths.append("")

        album_frame = tk.LabelFrame(self.scrollable_frame, text=f"Álbum {album_count}", padx=10, pady=10, font=('Helvetica', 10, 'bold'))
        album_frame.pack(fill=tk.X, expand=True, pady=5, padx=5)
        self.album_frames.append(album_frame)
        
        album_name_var = tk.StringVar()
        prefix_var = tk.StringVar()
        description_var = tk.StringVar() # Nova variável para a descrição
        file_label_var = tk.StringVar(value="Nenhum ficheiro selecionado")
        cover_label_var = tk.StringVar(value="Nenhuma capa selecionada (primeira da lista será usada)")

        self.albums_data.append({
            'album_name_var': album_name_var,
            'prefix_var': prefix_var,
            'description_var': description_var, # Adicionado
            'file_label_var': file_label_var,
            'cover_label_var': cover_label_var
        })

        # Frame para Nome do Álbum e Prefixo
        top_details_frame = tk.Frame(album_frame)
        top_details_frame.pack(fill=tk.X, pady=(0, 5))
        tk.Label(top_details_frame, text="Nome do Álbum:").pack(side=tk.LEFT)
        tk.Entry(top_details_frame, textvariable=album_name_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 15))
        tk.Label(top_details_frame, text="Prefixo das Fotos:").pack(side=tk.LEFT)
        tk.Entry(top_details_frame, textvariable=prefix_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        remove_button = tk.Button(top_details_frame, text="Remover", command=lambda idx=index: self.remove_album_form(idx), bg="#DC3545", fg="white")
        remove_button.pack(side=tk.RIGHT, padx=(10, 0))

        # Novo Frame para a Descrição
        description_frame = tk.Frame(album_frame)
        description_frame.pack(fill=tk.X, pady=(0, 5))
        tk.Label(description_frame, text="Descrição do Álbum:").pack(side=tk.LEFT)
        tk.Entry(description_frame, textvariable=description_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        collection_frame = tk.Frame(album_frame)
        collection_frame.pack(fill=tk.X, pady=5)
        tk.Label(collection_frame, text="Adicionar à Coleção:").pack(side=tk.LEFT)
        
        combobox_values = [c['title'] for c in self.collections_list] if self.collections_list else ["A buscar coleções..."]
        combobox = ttk.Combobox(collection_frame, state="readonly", values=combobox_values)
        if combobox_values:
            combobox.current(0)
        combobox.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.collection_comboboxes.append(combobox)

        files_frame = tk.Frame(album_frame)
        files_frame.pack(fill=tk.X, pady=(0, 5))
        tk.Button(files_frame, text="Selecionar Ficheiros...", command=lambda idx=index: self.select_files(idx)).pack(side=tk.LEFT)
        tk.Label(files_frame, textvariable=file_label_var, fg="blue", wraplength=400).pack(side=tk.LEFT, padx=10)

        cover_frame = tk.Frame(album_frame)
        cover_frame.pack(fill=tk.X)
        tk.Button(cover_frame, text="Selecionar Capa...", command=lambda idx=index: self.select_cover(idx)).pack(side=tk.LEFT)
        tk.Label(cover_frame, textvariable=cover_label_var, fg="darkgreen", wraplength=400).pack(side=tk.LEFT, padx=10)

    def remove_album_form(self, index_to_remove):
        if len(self.album_frames) <= 1:
            messagebox.showwarning("Aviso", "Não é possível remover o último formulário de álbum.")
            return

        current_data = []
        for i in range(len(self.albums_data)):
            if i == index_to_remove:
                continue
            
            data = self.albums_data[i]
            current_data.append({
                'name': data['album_name_var'].get(),
                'prefix': data['prefix_var'].get(),
                'description': data['description_var'].get(), # Guardar descrição
                'collection': self.collection_comboboxes[i].get(),
                'files': self.file_paths[i],
                'cover': self.cover_photo_paths[i],
            })

        for frame in self.album_frames:
            frame.destroy()

        self.album_frames.clear()
        self.albums_data.clear()
        self.file_paths.clear()
        self.cover_photo_paths.clear()
        self.collection_comboboxes.clear()

        for data in current_data:
            self.add_album_form()
            new_index = len(self.albums_data) - 1
            
            self.albums_data[new_index]['album_name_var'].set(data['name'])
            self.albums_data[new_index]['prefix_var'].set(data['prefix'])
            self.albums_data[new_index]['description_var'].set(data['description']) # Restaurar descrição
            
            if data['collection'] in self.collection_comboboxes[new_index]['values']:
                self.collection_comboboxes[new_index].set(data['collection'])

            self.file_paths[new_index] = data['files']
            if data['files']:
                self.albums_data[new_index]['file_label_var'].set(f"{len(data['files'])} ficheiros selecionados.")
            
            self.cover_photo_paths[new_index] = data['cover']
            if data['cover']:
                self.albums_data[new_index]['cover_label_var'].set(f"Capa: {os.path.basename(data['cover'])}")
        
        self.log_message(f"Formulário de álbum removido.")

    def authenticate_flickr(self):
        try:
            flickr_api.set_keys(api_key=CHAVE_API, api_secret=SEGREDO_API)
            
            if not os.path.exists(TOKEN_FILE):
                self.log_message("Ficheiro de token não encontrado. A iniciar autenticação...")
                
                a = flickr_api.auth.AuthHandler() 
                perms = 'write'
                url = a.get_authorization_url(perms)
                
                self.log_message("O seu navegador vai abrir para autorizar a aplicação.")
                self.log_message("Depois de autorizar, copie o código e cole na janela que aparecer.")
                
                import webbrowser
                webbrowser.open(url)
                
                verifier = simpledialog.askstring("Código de Verificação do Flickr", 
                                                  "Por favor, cole aqui o código do Flickr:",
                                                  parent=self.root)
                
                if not verifier:
                    self.log_message("Autenticação cancelada pelo utilizador.")
                    logging.warning("Processo de autenticação cancelado.")
                    return False
                
                self.log_message("A verificar o código...")
                a.set_verifier(verifier)
                a.save(TOKEN_FILE)
                self.log_message(f"Token de autenticação guardado em {TOKEN_FILE}")
                
                self.auth_handler = a
                flickr_api.set_auth_handler(self.auth_handler)
            else:
                self.log_message("Ficheiro de token encontrado. A carregar autenticação...")
                self.auth_handler = flickr_api.auth.AuthHandler.load(TOKEN_FILE)
                flickr_api.set_auth_handler(self.auth_handler)

            self.log_message("Autenticação com o Flickr bem-sucedida.")
            logging.info("Autenticação bem-sucedida.")
            return True
        except Exception as e:
            self.log_message(f"Erro na autenticação: {e}")
            logging.exception("Falha na autenticação.")
            if os.path.exists(TOKEN_FILE):
                 try:
                     os.remove(TOKEN_FILE)
                     self.log_message("Token antigo removido. Tente reiniciar a aplicação.")
                 except Exception as del_e:
                     self.log_message(f"Não foi possível remover o token inválido: {del_e}")
            return False

    def fetch_collections_thread(self):
        self.log_message("A buscar coleções do Flickr...")
        self.refresh_button.config(state='disabled', text="A buscar...")
        thread = threading.Thread(target=self.fetch_collections)
        thread.daemon = True
        thread.start()

    def fetch_collections(self):
        try:
            logging.debug("A tentar fazer login para buscar coleções...")
            user = flickr_api.test.login()
            if not user:
                self.log_message("ERRO: Não foi possível obter o utilizador autenticado.")
                logging.error("flickr_api.test.login() retornou None.")
                return

            logging.info(f"Utilizador autenticado: {user}")
            
            self.log_message("A usar user.getCollectionTree() para buscar coleções...")
            logging.debug("A usar user.getCollectionTree()...")
            
            collections_tree = user.getCollectionTree()
            
            parsed_collections = []
            if collections_tree:
                for collection in collections_tree:
                    try:
                        if hasattr(collection, 'title') and hasattr(collection, 'id'):
                            parsed_collections.append({
                                'title': collection.title,
                                'id': collection.id
                            })
                            logging.debug(f"Coleção encontrada: ID={collection.id}, Título={collection.title}")
                        else:
                            logging.warning(f"Item da árvore de coleções ignorado por não ter 'title' ou 'id': {collection}")
                    except Exception as parse_err:
                        logging.error(f"Erro ao processar um item da árvore de coleções: {parse_err} - Item: {collection}")

            self.collections_list = [{'title': "Nenhuma", 'id': None}] + parsed_collections
            
            self.log_message(f"Encontradas {len(self.collections_list) - 1} coleções.")
            logging.info(f"Processamento de coleções concluído. {len(parsed_collections)} coleções encontradas.")
            self.root.after(0, self.update_collection_comboboxes)

        except KeyError as e:
            if 'set' in str(e):
                msg = "ERRO: Encontrada uma coleção vazia no seu Flickr. Por favor, adicione pelo menos um álbum a cada coleção no site do Flickr para resolver este bug da biblioteca."
                self.log_message(msg)
                logging.error(msg, exc_info=True)
                messagebox.showerror("Erro da Biblioteca do Flickr", msg)
            else:
                logging.exception("Ocorreu uma excepção não tratada em fetch_collections:")
                self.log_message(f"ERRO ao buscar coleções: {e}")
        except Exception as e:
            logging.exception("Ocorreu uma excepção não tratada em fetch_collections:")
            self.log_message(f"ERRO ao buscar coleções: {e}")
        finally:
            self.root.after(0, lambda: self.refresh_button.config(state='normal', text="Atualizar Lista de Coleções do Flickr"))

    def update_collection_comboboxes(self):
        collection_titles = [c['title'] for c in self.collections_list]
        for combo in self.collection_comboboxes:
            combo['values'] = collection_titles
            if collection_titles:
                combo.current(0)

    def select_files(self, index):
        files = filedialog.askopenfilenames(
            title=f"Selecione as fotos para o Álbum {index+1}",
            filetypes=[("Imagens", "*.jpg *.jpeg *.png *.gif"), ("Todos os ficheiros", "*.*")]
        )
        if files:
            self.file_paths[index] = files
            self.albums_data[index]['file_label_var'].set(f"{len(files)} ficheiros selecionados.")
            self.log_message(f"[Álbum {index+1}] {len(files)} ficheiros selecionados.")

    def select_cover(self, index):
        file = filedialog.askopenfilename(
            title=f"Selecione a FOTO DE CAPA para o Álbum {index+1}",
            filetypes=[("Imagens", "*.jpg *.jpeg *.png *.gif"), ("Todos os ficheiros", "*.*")]
        )
        if file:
            self.cover_photo_paths[index] = file
            filename = os.path.basename(file)
            self.albums_data[index]['cover_label_var'].set(f"Capa: {filename}")
            self.log_message(f"[Álbum {index+1}] Foto de capa selecionada: {filename}")

    def log_message(self, message):
        logging.info(message)
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')
        self.root.update_idletasks()

    def update_timer(self):
        if self.timer_running:
            elapsed_seconds = time.time() - self.start_time
            hours, remainder = divmod(elapsed_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            self.timer_label.config(text=f"Tempo: {int(hours):02}:{int(minutes):02}:{int(seconds):02}")
            self.root.after(1000, self.update_timer)

    def start_upload_thread(self):
        is_any_album_valid = any(self.albums_data[i]['album_name_var'].get() and self.file_paths[i] for i in range(len(self.albums_data)))
        if not is_any_album_valid:
            messagebox.showwarning("Nada para Enviar", "Por favor, preencha o nome do álbum e selecione os ficheiros para pelo menos um dos álbuns.")
            return
        
        self.upload_button.config(state='disabled', text="A enviar...")
        
        self.start_time = time.time()
        self.timer_running = True
        self.update_timer()

        thread = threading.Thread(target=self.upload_process)
        thread.daemon = True
        thread.start()

    def upload_process(self):
        total_photos_uploaded_count = 0
        albums_created_count = 0
        try:
            user = flickr_api.test.login()
            if not user:
                self.log_message("ERRO CRÍTICO: Não foi possível autenticar o utilizador para o processo de upload.")
                logging.error("Falha ao obter o utilizador no início de upload_process.")
                return

            for i in range(len(self.albums_data)):
                album_title = self.albums_data[i]['album_name_var'].get()
                photo_prefix_title = self.albums_data[i]['prefix_var'].get()
                album_description = self.albums_data[i]['description_var'].get()
                image_files = list(self.file_paths[i])
                cover_photo_path = self.cover_photo_paths[i]

                if not album_title or not image_files:
                    continue
                
                albums_created_count += 1
                self.log_message(f"\n--- A INICIAR UPLOAD PARA O ÁLBUM {i+1}: '{album_title}' ---")
                
                primary_photo_object = None
                photos_uploaded_for_this_album = []
                prefix = photo_prefix_title if photo_prefix_title else album_title

                if cover_photo_path and os.path.exists(cover_photo_path):
                    self.log_message(f"A enviar foto de capa primeiro: {os.path.basename(cover_photo_path)}")
                    try:
                        photo = flickr_api.upload(photo_file=cover_photo_path, title=f"{prefix} - 000 (Capa)", is_public="0", safety_level="1")
                        if photo:
                            self.log_message(f"  -> Sucesso! Capa enviada. ID: {photo.id}")
                            primary_photo_object = photo
                            photos_uploaded_for_this_album.append(photo)
                            if cover_photo_path in image_files:
                                image_files.remove(cover_photo_path)
                        else:
                            self.log_message(f"  -> FALHA ao enviar capa. A primeira foto da lista será usada.")
                    except Exception as e:
                        self.log_message(f"  -> ERRO ao enviar capa: {e}. A primeira da lista será usada.")
                        logging.warning(f"Erro ao enviar capa para o álbum '{album_title}': {e}")
                
                for j, full_path in enumerate(image_files):
                    filename = os.path.basename(full_path)
                    new_title = f"{prefix} - {j+1:03d}"
                    self.log_message(f"A enviar foto ({j+1}/{len(image_files)}): {filename}")
                    try:
                        photo = flickr_api.upload(photo_file=full_path, title=new_title, is_public="0", safety_level="1")
                        if photo:
                            self.log_message(f"  -> Sucesso! ID da foto: {photo.id}")
                            photos_uploaded_for_this_album.append(photo)
                            if primary_photo_object is None:
                                primary_photo_object = photo
                        else:
                            self.log_message(f"  -> FALHA: O upload de '{filename}' retornou nulo.")
                    except Exception as upload_err:
                        self.log_message(f"  -> ERRO no upload de '{filename}': {upload_err}")
                        logging.warning(f"Falha no upload de {filename}: {upload_err}")

                if not primary_photo_object:
                    self.log_message(f"ERRO: Nenhuma foto pôde ser enviada para o álbum '{album_title}'. Criação do álbum cancelada.")
                    logging.error(f"Nenhuma foto enviada para o álbum '{album_title}'.")
                    continue

                try:
                    self.log_message(f"A criar o álbum '{album_title}' com a capa '{primary_photo_object.title}'...")
                    photoset = flickr_api.Photoset.create(title=album_title, primary_photo=primary_photo_object, description=album_description)
                    
                    for p in photos_uploaded_for_this_album:
                        if p.id != primary_photo_object.id:
                            photoset.addPhoto(photo=p)
                    self.log_message(f"Álbum '{album_title}' criado com {len(photos_uploaded_for_this_album)} fotos.")
                    total_photos_uploaded_count += len(photos_uploaded_for_this_album)

                    selected_collection_title = self.collection_comboboxes[i].get()
                    if selected_collection_title and selected_collection_title != "Nenhuma":
                        collection_id = next((c['id'] for c in self.collections_list if c['title'] == selected_collection_title), None)
                        if collection_id:
                            try:
                                self.log_message(f"A adicionar álbum '{album_title}' à coleção '{selected_collection_title}'...")
                                
                                # SOLUÇÃO DEFINITIVA: Usar chamada de baixo nível para AMBAS as operações de coleção
                                # para contornar todos os bugs da biblioteca.
                                self.log_message(f"  -> A obter álbuns existentes da coleção (via API direta)...")

                                raw_response = flickr_api.method_call.call_api(
                                    method='flickr.collections.getTree',
                                    collection_id=collection_id,
                                    user_id=user.id,
                                    format='json',
                                    nojsoncallback=1,
                                    auth_handler=self.auth_handler
                                )
                                logging.debug(f"Resposta da API para getTree da coleção '{collection_id}': {raw_response}")
                                
                                existing_photoset_ids = []
                                if 'collections' in raw_response and raw_response['collections'] and 'collection' in raw_response['collections']:
                                    collection_list_api = raw_response['collections']['collection']
                                    if isinstance(collection_list_api, dict):
                                        collection_list_api = [collection_list_api]
                                    
                                    if collection_list_api and 'set' in collection_list_api[0]:
                                        album_list = collection_list_api[0]['set']
                                        if isinstance(album_list, dict):
                                            album_list = [album_list]
                                        for album_dict in album_list:
                                            if 'id' in album_dict:
                                                existing_photoset_ids.append(album_dict['id'])
                                
                                self.log_message(f"  -> Encontrados {len(existing_photoset_ids)} álbuns existentes.")
                                
                                all_photoset_ids = existing_photoset_ids + [photoset.id]
                                photoset_ids_str = ",".join(all_photoset_ids)
                                
                                self.log_message(f"  -> A atualizar a coleção com a nova lista de álbuns...")
                                
                                flickr_api.method_call.call_api(
                                    method='flickr.collections.editSets',
                                    collection_id=collection_id,
                                    photoset_ids=photoset_ids_str,
                                    auth_handler=self.auth_handler
                                )
                                self.log_message("  -> Sucesso!")

                            except Exception as add_coll_err:
                                self.log_message(f"  -> ERRO ao adicionar à coleção: {add_coll_err}")
                                logging.warning(f"Erro ao adicionar álbum à coleção: {add_coll_err}", exc_info=True)

                except Exception as album_err:
                    self.log_message(f"ERRO CRÍTICO ao criar álbum '{album_title}': {album_err}")
                    logging.exception(f"Erro ao criar o álbum '{album_title}'.")

            self.log_message(f"\n--- PROCESSO CONCLUÍDO! ---")
            messagebox.showinfo("Sucesso", f"Processo finalizado.\n\n- {albums_created_count} álbuns processados.\n- {total_photos_uploaded_count} fotos enviadas no total.")

        except Exception as e:
            error_msg = f"Ocorreu um erro inesperado: {e}"
            self.log_message(f"ERRO: {error_msg}")
            logging.exception("Erro inesperado no processo de upload.")
            messagebox.showerror("Erro Crítico", error_msg)
        finally:
            self.upload_button.config(state='normal', text="Iniciar Upload de Todos os Álbuns")
            self.timer_running = False

if __name__ == "__main__":
    root = tk.Tk()
    app = FlickrUploaderApp(root)
    root.mainloop()

