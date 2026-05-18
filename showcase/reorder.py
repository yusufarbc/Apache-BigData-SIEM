import re
import json

# Read the HTML file
with open("index.html", "r", encoding="utf-8") as f:
    html_content = f.read()

# Find the slides container
slides_start = html_content.find('<div class="page" id="slides">')
slides_end = html_content.find('  </div>\n\n  <script>')

if slides_start == -1 or slides_end == -1:
    print("Could not find slides container.")
    exit(1)

slides_html = html_content[slides_start + 32:slides_end]

# We can split sections by "<!-- SLIDE"
sections = re.split(r'(?=<!-- SLIDE)', slides_html)

# Clean up sections (remove empty ones)
sections = [s for s in sections if s.strip()]

# Current order is:
# 0: SLIDE 1 (Hero)
# 1: SLIDE 2 (The Problem)
# 2: SLIDE 3 (Data Source)
# 3: SLIDE 4 (Python Producer)
# 4: SLIDE 5 (Kafka)
# 5: SLIDE 6 (Spark)
# 6: SLIDE 7 (Hadoop)
# 7: SLIDE 8 (Hive)
# 8: SLIDE 9 (Zeppelin)
# 9: SLIDE 10 (Superset)
# 10: SLIDE 11 (Postgres/Redis)
# 11: SLIDE 12 (Feature Engineering)
# 12: SLIDE 13 (Math)
# 13: SLIDE 14 (Retraining)
# 14: SLIDE 15 (Metrics)
# 15: SLIDE 16 (SIEM Rules)
# 16: SLIDE 17 (Scatter)
# 17: SLIDE 18 (Full Architecture)
# 18: SLIDE 19 (Full Cluster)
# 19: SLIDE 20 (Docker Services)
# 20: SLIDE 21 (ETL Code)
# 21: SLIDE 22 (Dashboard View)
# 22: SLIDE 23 (Validation)
# 23: SLIDE 24 (Vision/Thanks)

# We want new order:
# 0: Hero (0)
# 1: Problem (1)
# 2: Full Architecture (17) -> Renumber 3
# 3: Full Cluster (18) -> Renumber 4
# 4: Data Source (2) -> Renumber 5
# 5: Python Producer (3) -> Renumber 6
# 6: Kafka (4) -> Renumber 7
# 7: Spark (5) -> Renumber 8
# 8: Hadoop (6) -> Renumber 9
# 9: Hive (7) -> Renumber 10
# 10: Zeppelin (8) -> Renumber 11
# 11: Superset (9) -> Renumber 12
# 12: Postgres/Redis (10) -> Renumber 13
# 13: Feature Engineering (11) -> Renumber 14
# 14: Math (12) -> Renumber 15
# 15: Retraining (13) -> Renumber 16
# 16: Scatter (16) -> Renumber 17
# 17: Metrics (14) -> Renumber 18
# 18: SIEM Rules (15) -> Renumber 19
# 19: Docker Services (19) -> Renumber 20
# 20: ETL Code (20) -> Renumber 21
# 21: Dashboard View (21) -> Renumber 22
# 22: Validation (22) -> Renumber 23
# 23: Vision/Thanks (23)

new_order_indices = [0, 1, 17, 18, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 16, 14, 15, 19, 20, 21, 22, 23]
new_sections = [sections[i] for i in new_order_indices]

# Now, we need to renumber the <h3> tags and update the titles/descriptions to make them much stronger
import re

def update_section(idx, html_str):
    if "<h3>" not in html_str:
        return html_str
    
    # Extract the h3 content
    h3_match = re.search(r'<h3>(.*?)</h3>', html_str)
    if not h3_match:
        return html_str
        
    old_title = h3_match.group(1)
    # Strip out the number
    title_text = re.sub(r'^\d+\)\s*', '', old_title)
    
    # Custom titles for stronger narrative
    if "Neden Big Data SIEM" in title_text:
        title_text = "Neden Big Data SIEM Geliştirdik?"
    elif "Uçtan Uca Veri Akış Mimarisi" in title_text:
        title_text = "Mimarinin Büyük Resmi: Uçtan Uca Veri Akışı"
    elif "Tüm Konteyner Haritası" in title_text:
        title_text = "Sistem Altyapısı: Dağıtık Küme Mimarisi"
    elif "SecRepo Siber Güvenlik Veri Kümeleri" in title_text:
        title_text = "Gerçek Dünya Verisi: SecRepo Logları"
    elif "Python Çoklu Dosya Paralel Üretici" in title_text:
        title_text = "Veri Toplama Hattı: Asenkron Python Üreticisi"
    elif "Apache Kafka" in title_text:
        title_text = "Tampon ve Mesajlaşma: Apache Kafka (KRaft)"
    elif "Apache Spark" in title_text:
        title_text = "Analiz Kalbi: Apache Spark Akış İşleme"
    elif "Apache Hadoop" in title_text:
        title_text = "Veri Gölü: Dağıtık HDFS Depolama"
    elif "Apache Hive" in title_text:
        title_text = "Veri Ambarı: Apache Hive & Parquet"
    elif "Apache Zeppelin" in title_text:
        title_text = "Etkileşimli Analiz: Apache Zeppelin"
    elif "Apache Superset" in title_text:
        title_text = "SOC Raporlama Paneli: Apache Superset"
    elif "PostgreSQL ve Redis" in title_text:
        title_text = "Performans ve Şema: PostgreSQL & Redis"
    elif "SecRepo Logları ve Öznitelik Mühendisliği" in title_text:
        title_text = "Siber Zeka: Öznitelik Mühendisliği (Feature Eng.)"
    elif "Matematiksel Altyapı" in title_text:
        title_text = "Siber Zeka: ML Matematiksel Altyapısı"
    elif "Canlı Eğitim Yapısı" in title_text:
        title_text = "Siber Zeka: Asenkron Canlı Model Eğitimi"
    elif "Görsel Analizi" in title_text:
        title_text = "Siber Zeka: Outlier Kümeleme (2D İzdüşüm)"
    elif "Kümeleme Başarımı" in title_text:
        title_text = "Model Doğrulaması: WSSSE ve Anomali Kararları"
    elif "Kural Tabanlı Tehdit Tespiti" in title_text:
        title_text = "Deterministik Yaklaşım: SIEM Kuralları"
    elif "Docker Mikroservisleri" in title_text:
        title_text = "Konteyner Orkestrasyonu: Docker Servis Haritası"
    elif "ETL ve Zenginleştirme" in title_text:
        title_text = "Spark Kod Mimarisi: ETL & GeoIP Zenginleştirme"
    elif "Raporlama Görünümü" in title_text:
        title_text = "SOC Paneli: Canlı Siber İstihbarat Ekranı"
    elif "Küme Sağlık Raporu" in title_text:
        title_text = "Canlı Sistem Doğrulaması ve Teşhis (CLI)"
    
    new_title = f"{idx}) {title_text}"
    html_str = html_str.replace(f"<h3>{old_title}</h3>", f"<h3>{new_title}</h3>")
    return html_str

for i, section in enumerate(new_sections):
    if i > 0 and i < len(new_sections) - 1:
        new_sections[i] = update_section(i, new_sections[i])


# Update texts inside paragraphs to be much stronger
text_replacements = {
    "Geleneksel SIEM ve log yönetim çözümleri veri hacmi (EPS) arttıkça lisanslama maliyetleri, disk darboğazı ve CPU limitlerine takılır. Bizim geliştirdiğimiz Big Data SIEM mimarisi bu sorunları kökten çözer:": "Saniyede milyonlarca olayın (EPS) aktığı modern ağlarda, geleneksel SIEM'ler astronomik lisans maliyetleri ve donanım darboğazlarına yenik düşer. Geliştirdiğimiz bu açık kaynaklı devasa Big Data SIEM mimarisi, sınırları yıkarak bu sorunları kökten çözmektedir:",
    
    "Sistemde işlenen veriler, yapay loglar yerine <strong>SecRepo.com</strong> siber güvenlik veri kümesi deposundan alınan gerçek dünya ağ akışlarıdır:": "Sistemimizin ispatı için izole yapay veriler değil, siber güvenlik araştırmacılarının altın standardı olan <strong>SecRepo.com</strong> üzerindeki, sızma ve tarama saldırılarını organik barındıran devasa gerçek dünya ağ trafiği (Zeek/Snort) işlenmektedir:",
    
    "SecRepo veri gölündeki statik log dosyaları, geliştirdiğimiz asenkron Python veri üreticisiyle dinamik olarak akışa dahil edilir:": "Bu devasa veri kümesini sisteme organik bir ağ trafiğiymiş gibi akıtmak için, eş zamanlı (multi-threaded) çalışan ve mikrosaniye hassasiyetinde canlı log simülasyonu yapan özel bir Python Ingestion Engine (Veri Üreticisi) kodlanmıştır:",
    
    "Apache Kafka, siber güvenlik loglarının toplanması ve dağıtılmasında yüksek throughput sağlayan sinir sistemi katmanımızdır:": "Apache Kafka, devasa siber saldırılardaki veri fırtınalarını (EPS patlamalarını) emen, kayıpsız ileten ve sistemin çökmesini engelleyen ultra hızlı sinir ağımızdır:",
    
    "Apache Spark, bellek içi (In-Memory) ve dağıtık veri işleme kabiliyetiyle SIEM sistemimizin kalbidir:": "Dağıtık mimarimizin beyni olan Apache Spark; belleği (In-Memory) doğrudan kullanarak saniyeler altı reaksiyon süresiyle milyonlarca logu işler, temizler (ETL) ve makine öğrenmesi algoritmalarını paralel koşturur:",
    
    "Hadoop Dağıtık Dosya Sistemi (HDFS), petabaytlarca siber güvenlik logunun yatayda genişleyen disk havuzlarında depolanmasını sağlar:": "Petabaytlarca ağ logunu ve anomali geçmişini asla kaybetmemek adına, veriyi birden fazla sunucuya klonlayarak (replication) hata toleransını zirveye taşıyan HDFS (Hadoop) kullanılmıştır:",
    
    "HDFS üzerindeki optimize edilmiş Parquet dosyalarını ilişkisel SQL tabloları olarak sorgulamamızı sağlayan ambar katmanıdır:": "HDFS üzerinde yatan ham devasa dosyaları, milisaniyelik hızla sorgulanabilen SQL tablolarına dönüştüren zeka katmanımız Apache Hive'dır:",
    
    "Veri analistleri ve siber güvenlik araştırmacıları için interaktif notebook ve veri keşif aracıdır:": "Güvenlik analistlerinin (SOC) milyarlarca satır arasında saniyeler içinde tehdit avcılığı (Threat Hunting) yapabilmesi için kurulan interaktif PySpark sorgu laboratuvarımızdır:",
    
    "Apache Superset, analiz sonuçlarını görselleştirmek için kullanılan arayüz katmanıdır. Hive Server2 JDBC katmanı üzerinden doğrudan veri gölüne bağlanır:": "Karmaşık büyük veri operasyonlarının sonuçlarını, karar vericiler ve yöneticiler için saniyeler içinde anlaşılır görsel bir ziyafete dönüştüren, canlı komuta kontrol (SOC) raporlama merkezimizdir:",
    
    "Dağıtık mimarimizin kararlılığı ve performansı, bu iki yardımcı katman sayesinde optimize edilir:": "Bu devasa dağıtık orkestranın ışık hızında çalışması ve sunum grafiklerinin anında yüklenmesi için kritik altyapı ivmelendiricilerimiz:"
}

for i in range(len(new_sections)):
    for old_text, new_text in text_replacements.items():
        new_sections[i] = new_sections[i].replace(old_text, new_text)

# Reassemble slides
new_slides_html = "\n".join(new_sections)
new_html_content = html_content[:slides_start + 32] + "\n" + new_slides_html + "\n" + html_content[slides_end:]

# Now re-generate speaker notes to match exactly the new layout
new_speaker_notes = [
    "Değerli jüri üyeleri, bugün sizlere büyük veri ve yapay zeka ile güçlendirilmiş, gerçek zamanlı çalışan SIEM ve ağ anomali tespit mimarimizi sunacağım. Sistemin kod yapısını ve vizyonunu uçtan uca aktaracağım.",
    "Geleneksel SIEM'ler ağ hızı arttıkça lisans ve donanım darboğazına girer. Biz, dağıtık ve açık kaynaklı bir mimari kurarak limitsiz yatay ölçeklenen ve yapay zeka ile kendi kendine öğrenen bir sistem inşa ettik.",
    "Bileşenlere geçmeden önce büyük resmi görelim: Uçtan uca mimarimizde veriler Python ingestor ile toplanır, Kafka ile tamponlanır, Spark'ta canlı olarak ML ve Kural motorundan geçirilir, ardından HDFS/Hive'da kalıcı depolanıp Superset'te görselleşir.",
    "Bu diyagram, sistemin ağ mimarisini göstermektedir. PostgreSQL, Redis, Kafka, Hadoop ve Spark kümelerinin Docker üzerinden izole mikroservisler olarak birbirleriyle nasıl iletişim kurduğunu görüyoruz.",
    "Test verisi olarak sentetik loglar yerine SecRepo.com'daki gerçek dünya Zeek ve Snort loglarını kullandık. Bu sayede modelimiz gerçek sızmaları ve port taramalarını doğrudan öğrenmektedir.",
    "Bu devasa statik veriyi gerçek canlı bir ağ gibi sisteme pompalamak için özel bir Asenkron Python Üreticisi kodladık. Bu yazılım logları farklı dosyalardan aynı anda okuyarak dinamik Kafka kanallarına basmaktadır.",
    "Apache Kafka, sistemin şok emicisidir (shock absorber). Siber saldırı anlarındaki aşırı log yüklenmelerinde veriyi diskinde tamponlayarak, Spark analiz motorunun çökmesini engeller ve sıfır veri kaybını garanti eder.",
    "Sistemin beyni olan Apache Spark, Kafka'dan okuduğu akışları Catalyst ve Tungsten optimizasyonlarıyla mikrosaniyeler içinde analiz eder, GeoIP ekler ve ML kümelerine dağıtır.",
    "İşlenen tüm veri güvenle Apache Hadoop HDFS'te depolanır. Sunuculardan (DataNode) biri fiziksel olarak çökse bile veriler diğer sunucularda yedekli olduğundan sistem kesintisiz yaşamaya devam eder.",
    "Dağıtık ambarımız Hive, veriyi yatayda 'Parquet' formatında arşivler. İşletim yılı, ayı ve gününe göre bölümlenen (partitioned) loglar sayesinde petabaytlarca veride bile anında SQL sorgusu yapılabilir.",
    "Zeppelin defterleri, siber tehdit avcılarının (Threat Hunters) anlık veriler veya uzun dönem geçmiş kayıtlar üzerinde PySpark kodları ve ANSI SQL çalıştırarak yeni anomali paternleri bulmasını sağlar.",
    "Superset, verilerin son durağıdır. Kurduğumuz K-Means modelinin çıktılarını, canlı alarmları ve Coğrafi GeoIP ısı haritalarını jüri önünde sergileyeceğimiz görsel bir operasyon merkezidir.",
    "Bu görsel hızın arkasında Redis ve PostgreSQL yatar. PostgreSQL devasa Hive tablolarının haritasını saklarken, Redis saniyede binlerce gelen istek karşısında grafikleri önbellekleyerek anında render eder.",
    "Yapay zeka (ML) hazırlığında ağ loglarındaki duration ve bytelar arası ciddi uçurumları (çarpıklığı) ezmek için log1p (logaritma + 1) dönüşümü kullandık ve port değerini dışladık.",
    "Matematiksel olarak model, gelen akışları StandardScaler (Z-Skor) ile eşit ağırlıklı hale getirip, verileri 8 farklı K-Means küme merkezine ($\mu_i$) olan Öklid mesafesine göre değerlendirir.",
    "Concept Drift yani 'Değişen Davranış' problemini çözmek için modelimiz canlı olarak sürekli yeniden eğitilir. İlk 100 kayıtta öğrenen model, her 50 batch'te kendini tazeleyerek siber dünyadaki yeni taktiklere uyum sağlar.",
    "Bu 2 Boyutlu izdüşüm grafiği anomali tespiti mantığımızı özetler. Merkeze yakın yeşil noktalar sağlıklı işlemleri; 3.0 Öklid mesafesini aşarak fırlayan kırmızı noktalar ise kritik anomali alarmlarını temsil eder.",
    "Model kararlılığı (WSSSE metrikleri) veri gölüne anlık yazılır. Tablodaki hatanın zamanla düşmesi modelin öğrendiğini ispatlarken, mesafe tabanlı dinamik eşikler sayesinde false-positive oranı sıfıra yaklaşır.",
    "Yapay zekanın atlayabileceği spesifik sızma atakları (Dizin Geçişi, Port Tarama) için Spark içinde deterministik bir SIEM kural motoru devreye girer. Tehdit istihbaratı anlık eşleşir.",
    "Bu devasa sistemin mimari özeti ekrandadır. Gördüğünüz gibi 11 farklı konteyner, kendilerine has portlarda eşzamanlı çalışarak saniyeler altı SIEM reaksiyonu sağlamaktadır.",
    "Spark tarafındaki kodumuzun özeti burada yer alıyor. Regex ile ham veriden IP çekilmesi, if/else mantıklarıyla GeoIP simülasyonu yapılması ve Parquet bölümlemesi doğrudan bu kod üzerinden koşmaktadır.",
    "Tüm analiz ve kural motorumuzun birleşimi olan Canlı Kontrol Paneli'nde (SOC), aktif alarmları, anomali tespiti lokasyonlarını ve eşleşen log sayılarını anlık bir izleme ekranıyla takip ediyoruz.",
    "Projemizin çalışır durumda olduğunu HDFS canlı raporları, Kafka CLI akış testleri ve Hive JDBC SQL bağlantıları ile anlık konsol çıktıları üzerinden jüriye doğrulayabiliyoruz. Teşekkürler."
]

import json
notes_js = "    const speakerNotes = " + json.dumps(new_speaker_notes, indent=6, ensure_ascii=False) + ";\n"

# Replace old speakerNotes definition
old_notes_start = new_html_content.find('const speakerNotes = [')
old_notes_end = new_html_content.find('];', old_notes_start) + 2

new_html_content = new_html_content[:old_notes_start] + notes_js.strip() + "\n" + new_html_content[old_notes_end:]

# Write to file
with open("index.html", "w", encoding="utf-8") as f:
    f.write(new_html_content)

print("HTML reordered and updated successfully.")
