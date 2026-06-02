import urllib.request
import os

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    vendor_dir = os.path.join(base_dir, 'static', 'js', 'vendor')
    os.makedirs(vendor_dir, exist_ok=True)
    chartjs_path = os.path.join(vendor_dir, 'chart.js')

    url = 'https://cdn.jsdelivr.net/npm/chart.js/dist/chart.umd.min.js'
    print(f"Downloading {url} to {chartjs_path}...")
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req) as response:
            content = response.read().decode('utf-8')
        # Strip sourceMappingURL comments to prevent WhiteNoise collectstatic MissingFileError
        clean_content = '\n'.join([line for line in content.split('\n') if not line.strip().startswith('//# sourceMappingURL=')])
        with open(chartjs_path, 'w', encoding='utf-8') as out_file:
            out_file.write(clean_content)
        print("Chart.js downloaded successfully!")
    except Exception as e:
        print(f"Error downloading Chart.js: {e}")

if __name__ == '__main__':
    main()
