/**
 * FoodLens CBIR — Frontend Application Controller
 * Handles drag-and-drop uploads, AJAX API requests, and dynamic result rendering.
 */

document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("fileInput");
  const browseBtn = document.getElementById("browseBtn");
  const dropzoneEmpty = document.getElementById("dropzoneEmpty");
  const dropzonePreview = document.getElementById("dropzonePreview");
  const previewImg = document.getElementById("previewImg");
  const removeImgBtn = document.getElementById("removeImgBtn");
  const searchBtn = document.getElementById("searchBtn");

  const resultsPlaceholder = document.getElementById("resultsPlaceholder");
  const loadingState = document.getElementById("loadingState");
  const resultsList = document.getElementById("resultsList");
  const resultsInfo = document.getElementById("resultsInfo");
  const timeBadge = document.getElementById("timeBadge");

  const intermediateCard = document.getElementById("intermediateCard");
  const queryThumb = document.getElementById("queryThumb");
  const maskThumb = document.getElementById("maskThumb");
  const colorsPalette = document.getElementById("colorsPalette");
  const dbStatsBadge = document.getElementById("dbStatsBadge");
  const queryFeatureVector = document.getElementById("queryFeatureVector");
  const queryFeatureNote = document.getElementById("queryFeatureNote");

  let selectedFile = null;
  let previewUrl = null;

  // 1. Fetch System Stats on Mount
  fetch("/api/stats")
    .then((res) => res.json())
    .then((data) => {
      if (data.success && dbStatsBadge) {
        dbStatsBadge.textContent = `🗄️ ${data.total_images} món ăn · ${data.total_categories} nhóm`;
      }
    })
    .catch((err) => console.warn("Could not fetch stats:", err));

  // 2. Dropzone & File Selection Handlers
  browseBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    fileInput.click();
  });

  dropzone.addEventListener("click", () => {
    if (!selectedFile) {
      fileInput.click();
    }
  });

  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });

  dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("dragover");
  });

  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFile(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFile(e.target.files[0]);
    }
  });

  removeImgBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    resetUploadState();
  });

  function handleFile(file) {
    if (!file.type.startsWith("image/")) {
      alert("Vui lòng chọn một tệp hình ảnh hợp lệ (JPG, PNG, WEBP).");
      return;
    }

    const nextPreviewUrl = URL.createObjectURL(file);
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }
    previewUrl = nextPreviewUrl;
    selectedFile = file;
    previewImg.src = previewUrl;
    dropzoneEmpty.classList.add("hidden");
    dropzonePreview.classList.remove("hidden");
    searchBtn.disabled = false;
  }

  function resetUploadState() {
    selectedFile = null;
    fileInput.value = "";
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      previewUrl = null;
    }
    previewImg.src = "";
    dropzonePreview.classList.add("hidden");
    dropzoneEmpty.classList.remove("hidden");
    searchBtn.disabled = true;
  }

  // 3. Search Action Handler
  searchBtn.addEventListener("click", executeSearch);

  async function executeSearch() {
    if (!selectedFile) return;

    // UI State: Loading
    searchBtn.disabled = true;
    resultsPlaceholder.classList.add("hidden");
    resultsList.classList.add("hidden");
    intermediateCard.classList.add("hidden");
    resultsInfo.classList.add("hidden");
    loadingState.classList.remove("hidden");

    const formData = new FormData();
    formData.append("query_image", selectedFile);
    formData.append("top_k", "5");

    try {
      const response = await fetch("/api/search", {
        method: "POST",
        body: formData,
      });

      const data = await response.json();
      loadingState.classList.add("hidden");
      searchBtn.disabled = false;

      if (!data.success) {
        alert("Lỗi tìm kiếm: " + (data.error || "Không thể thực hiện truy vấn."));
        resultsPlaceholder.classList.remove("hidden");
        return;
      }

      // Render Visual Intermediate Results
      renderIntermediateResults(data);

      // Render Top-K Matches
      renderResultsList(data.results, data.elapsed_ms);
      if (dbStatsBadge && data.total_images) {
        fetch("/api/stats")
          .then((res) => res.json())
          .then((stats) => {
            if (stats.success) {
              dbStatsBadge.textContent =
                `🗄️ ${stats.total_images} món ăn · ${stats.total_categories} nhóm`;
            }
          })
          .catch((err) => console.warn("Could not refresh stats:", err));
      }

    } catch (err) {
      console.error("Search error:", err);
      loadingState.classList.add("hidden");
      searchBtn.disabled = false;
      resultsPlaceholder.classList.remove("hidden");
      alert("Đã xảy ra lỗi kết nối với máy chủ tìm kiếm: " + err.message);
    }
  }

  // 4. Render Intermediate Artifacts
  function renderIntermediateResults(data) {
    if (data.query_image_base64) {
      queryThumb.src = data.query_image_base64;
    }
    if (data.query_mask_base64) {
      maskThumb.src = data.query_mask_base64;
    }

    // Dominant Colors
    colorsPalette.innerHTML = "";
    if (data.dominant_colors && data.dominant_colors.length > 0) {
      data.dominant_colors.forEach((col) => {
        const swatch = document.createElement("div");
        swatch.className = "color-swatch";
        swatch.style.backgroundColor = col.hex;
        swatch.title = `Màu ${col.hex} · ${col.percent}%`;
        const hexLabel = document.createElement("span");
        hexLabel.textContent = col.hex;
        const percentLabel = document.createElement("span");
        percentLabel.textContent = `${col.percent}%`;
        swatch.append(hexLabel, percentLabel);
        colorsPalette.appendChild(swatch);
      });
    }

    const varianceMetric = document.getElementById("pcaVarianceMetric");
    if (varianceMetric && data.feature_breakdown) {
      varianceMetric.textContent =
        `1.460D → ${data.feature_breakdown.pca_dim} chiều ` +
        `· Giữ lại ${data.feature_breakdown.pca_variance_pct}% phương sai`;
    }
    renderFeatureVector(queryFeatureVector, data.query_pca_features);
    if (queryFeatureNote && Array.isArray(data.query_pca_features)) {
      queryFeatureNote.textContent =
        `${data.query_pca_features.length} chiều PCA chuẩn hóa L₂ dùng để so khớp · làm tròn 4 chữ số.`;
    }

    intermediateCard.classList.remove("hidden");
  }

  function renderFeatureVector(container, values) {
    if (!container) return;
    container.replaceChildren();

    if (!Array.isArray(values)) return;
    const vector = document.createElement("dl");
    vector.className = "feature-vector-grid";
    vector.setAttribute("aria-label", "Các thành phần vector PCA chuẩn hóa");

    values.forEach((value, index) => {
      const item = document.createElement("div");
      const dimension = document.createElement("dt");
      dimension.textContent = `PC${index + 1}`;
      const featureValue = document.createElement("dd");
      const numericValue = Number(value);
      featureValue.textContent = Number.isFinite(numericValue)
        ? numericValue.toFixed(4)
        : "—";
      item.append(dimension, featureValue);
      vector.appendChild(item);
    });

    container.appendChild(vector);
  }

  // 5. Render Ranked Results Cards
  function renderResultsList(results, elapsedMs) {
    resultsList.innerHTML = "";

    if (!results || results.length === 0) {
      const emptyMessage = document.createElement("p");
      emptyMessage.className = "placeholder-desc";
      emptyMessage.textContent = "Không tìm thấy kết quả phù hợp.";
      resultsList.appendChild(emptyMessage);
      resultsList.classList.remove("hidden");
      return;
    }

    timeBadge.textContent = `⚡ ${(elapsedMs / 1000).toFixed(2)} giây`;
    resultsInfo.classList.remove("hidden");

    results.forEach((item) => {
      const card = document.createElement("div");
      const rank = Number(item.rank);
      card.className = `result-card rank-${rank}`;

      // Rank styling
      let rankClass = "normal";
      if (rank === 1) rankClass = "gold";
      else if (rank === 2) rankClass = "silver";
      else if (rank === 3) rankClass = "bronze";

      const imageBox = document.createElement("div");
      imageBox.className = "result-img-box";
      const image = document.createElement("img");
      image.src = item.image_url;
      image.alt = item.dish_name;
      image.loading = "lazy";
      const rankBadge = document.createElement("span");
      rankBadge.className = `rank-badge ${rankClass}`;
      rankBadge.textContent = `#${rank}`;
      imageBox.append(image, rankBadge);

      const body = document.createElement("div");
      body.className = "result-body";
      const title = document.createElement("h3");
      title.className = "result-title";
      title.textContent = item.dish_name;
      const category = document.createElement("span");
      category.className = "result-category";
      category.textContent = `Danh mục: ${item.category}`;

      const barWrap = document.createElement("div");
      barWrap.className = "similarity-bar-wrap";
      const barMeta = document.createElement("div");
      barMeta.className = "similarity-bar-meta";
      const barLabel = document.createElement("span");
      const score = Number(item.cosine_score);
      const safeScore = Number.isFinite(score) ? Math.max(-1, Math.min(1, score)) : -1;
      const rawPercent = Number(item.similarity_pct);
      const similarityPercent = Number.isFinite(rawPercent)
        ? Math.max(0, Math.min(100, rawPercent))
        : ((safeScore + 1) / 2) * 100;
      barLabel.textContent = "Mức độ tương đồng";
      const scoreLabel = document.createElement("strong");
      scoreLabel.textContent = `${similarityPercent.toFixed(1)}%`;
      barMeta.append(barLabel, scoreLabel);
      const barBackground = document.createElement("div");
      barBackground.className = "similarity-bar-bg";
      const barFill = document.createElement("div");
      barFill.className = "similarity-bar-fill";
      barFill.style.width = `${similarityPercent}%`;
      barBackground.appendChild(barFill);
      barWrap.append(barMeta, barBackground);

      const featureDetails = document.createElement("details");
      featureDetails.className = "feature-details result-feature-details";
      const featureSummary = document.createElement("summary");
      featureSummary.textContent = "Hiển thị vector PCA của ảnh kết quả";
      const featureNote = document.createElement("p");
      featureNote.className = "feature-vector-note";
      const featureCount = Array.isArray(item.pca_features) ? item.pca_features.length : 0;
      featureNote.textContent =
        `Vector từ dòng tương ứng trong cơ sở dữ liệu · ${featureCount} chiều PCA chuẩn hóa L₂ · làm tròn 4 chữ số.`;
      const featureVector = document.createElement("div");
      featureVector.className = "feature-vector-scroll";
      renderFeatureVector(featureVector, item.pca_features);
      featureDetails.append(featureSummary, featureNote, featureVector);

      body.append(title, category, barWrap, featureDetails);
      card.append(imageBox, body);

      resultsList.appendChild(card);
    });

    resultsList.classList.remove("hidden");
  }
});
