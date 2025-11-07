from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import subprocess
import os
import uuid
import threading
from pathlib import Path
import json
import time

app = Flask(__name__)
CORS(app)

DOWNLOAD_FOLDER = "downloads"
Path(DOWNLOAD_FOLDER).mkdir(exist_ok=True)

# TOR proxy (IP rotation के लिए)
TOR_PROXY = "socks5://127.0.0.1:9050"

@app.route('/')
def index():
    return jsonify({'status': '✅ Backend is running! 🎬'})

@app.route('/api/info', methods=['POST'])
def get_video_info():
    """Video की info लाओ (सभी quality के साथ)"""
    data = request.json
    youtube_url = data.get('url', '').strip()
    
    if not youtube_url:
        return jsonify({'success': False, 'message': 'URL खाली है'}), 400
    
    try:
        # yt-dlp से video info निकालो
        command = [
            "yt-dlp",
            "-j",
            youtube_url
        ]
        
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            video_data = json.loads(result.stdout)
            
            # सभी formats filter करो
            formats = []
            
            if 'formats' in video_data:
                for fmt in video_data['formats']:
                    if fmt.get('vcodec') != 'none' and fmt.get('acodec') != 'none':
                        formats.append({
                            'format_id': fmt.get('format_id'),
                            'quality': fmt.get('format_note', 'Unknown'),
                            'resolution': f"{fmt.get('width', 0)}x{fmt.get('height', 0)}",
                            'fps': fmt.get('fps', 'Unknown'),
                            'filesize': fmt.get('filesize', 0),
                            'ext': fmt.get('ext', 'Unknown')
                        })
            
            return jsonify({
                'success': True,
                'title': video_data.get('title', 'Unknown'),
                'duration': video_data.get('duration', 0),
                'thumbnail': video_data.get('thumbnail', ''),
                'uploader': video_data.get('uploader', 'Unknown'),
                'formats': formats[:10]
            })
        else:
            return jsonify({'success': False, 'message': 'Video info load नहीं हो सकी'}), 400
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def download_video():
    """Video को selected quality में download करो"""
    data = request.json
    youtube_url = data.get('url', '').strip()
    format_id = data.get('format_id', 'best')
    
    if not youtube_url:
        return jsonify({'success': False, 'message': 'URL खाली है'}), 400
    
    # Unique ID हर download के लिए
    download_id = str(uuid.uuid4())
    download_path = os.path.join(DOWNLOAD_FOLDER, download_id)
    os.makedirs(download_path, exist_ok=True)
    
    def download_in_background():
        """Background में download करो"""
        try:
            output_template = os.path.join(download_path, "%(title)s.%(ext)s")
            
            command = [
                "yt-dlp",
                "-f", f"{format_id}+bestaudio/best",
                "-o", output_template,
                "--socket-timeout", "30",
                "--retries", "3",
                youtube_url
            ]
            
            result = subprocess.run(command, capture_output=True, text=True, timeout=600)
            
            if result.returncode == 0:
                files = os.listdir(download_path)
                if files:
                    filename = files[0]
                    file_path = os.path.join(download_path, filename)
                    file_size = os.path.getsize(file_path) / (1024 * 1024)
                    
                    with open(os.path.join(download_path, 'info.txt'), 'w') as f:
                        f.write(f"filename:{filename}\n")
                        f.write(f"size:{file_size:.2f}\n")
                        f.write(f"status:success\n")
            else:
                with open(os.path.join(download_path, 'info.txt'), 'w') as f:
                    f.write(f"status:error\n")
                    f.write(f"message:Download failed\n")
        except Exception as e:
            with open(os.path.join(download_path, 'info.txt'), 'w') as f:
                f.write(f"status:error\n")
                f.write(f"message:{str(e)}\n")
    
    thread = threading.Thread(target=download_in_background)
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True, 'download_id': download_id})

@app.route('/api/status/<download_id>')
def check_status(download_id):
    """Download की status check करो"""
    info_file = os.path.join(DOWNLOAD_FOLDER, download_id, 'info.txt')
    
    if not os.path.exists(info_file):
        return jsonify({'status': 'processing'})
    
    try:
        with open(info_file, 'r') as f:
            lines = f.readlines()
        
        info = {}
        for line in lines:
            if ':' in line:
                key, value = line.split(':', 1)
                info[key.strip()] = value.strip()
        
        return jsonify(info)
    except:
        return jsonify({'status': 'error'})

@app.route('/api/download/<download_id>/<filename>')
def get_download(download_id, filename):
    """File download करो"""
    file_path = os.path.join(DOWNLOAD_FOLDER, download_id, filename)
    
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    
    return jsonify({'error': 'File not found'}), 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
