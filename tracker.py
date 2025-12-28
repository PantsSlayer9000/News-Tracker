<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    html, body { height: 100%; margin: 0; padding: 0; background: transparent; overflow: hidden; }
    body{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
      color: #0f172a;
      line-height: 1.45;
    }
    .wrap{ height: 100%; padding: 14px; box-sizing: border-box; }
    .panel{
      height: 100%;
      display: flex;
      flex-direction: column;
      background: rgba(255,255,255,0.86);
      border: 1px solid rgba(15, 23, 42, 0.10);
      border-radius: 18px;
      box-shadow: 0 14px 30px rgba(15, 23, 42, 0.10);
      overflow: hidden;
    }
    .header{ padding: 14px; border-bottom: 1px solid rgba(15, 23, 42, 0.08); }
    .controls{ display: flex; gap: 10px; align-items: flex-end; flex-wrap: wrap; }
    .control{ flex: 1; min-width: 240px; }
    .control.small{ flex: 0; min-width: 200px; }
    .control.btn{ flex: 0; min-width: 140px; }
    .label{ font-size: 12px; color: rgba(15, 23, 42, 0.65); margin: 0 0 6px 0; }
    input, select, button{
      width: 100%;
      box-sizing: border-box;
      border: 1px solid rgba(15, 23, 42, 0.12);
      border-radius: 12px;
      padding: 10px 12px;
      font-size: 14px;
      background: rgba(255,255,255,0.92);
      color: #0f172a;
      outline: none;
    }
    button{
      background: #0f172a;
      color: #ffffff;
      border: 1px solid #0f172a;
      font-weight: 700;
      cursor: pointer;
    }
    .status{ margin-top: 10px; font-size: 13px; color: rgba(15, 23, 42, 0.65); }
    .list{ flex: 1; overflow: auto; padding: 12px 14px 14px 14px; box-sizing: border-box; }
    .card{
      background: rgba(255,255,255,0.94);
      border: 1px solid rgba(15, 23, 42, 0.10);
      border-radius: 14px;
      padding: 14px;
      margin-bottom: 12px;
    }
    .meta{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      margin-bottom: 8px;
      font-size: 12px;
      color: rgba(15, 23, 42, 0.62);
    }
    .pill{
      display: inline-block;
      padding: 4px 10px;
      border-radius: 999px;
      border: 1px solid rgba(15, 23, 42, 0.12);
      background: rgba(15, 23, 42, 0.03);
      color: #0f172a;
      font-weight: 700;
      font-size: 12px;
    }
    .title{ margin: 0; font-size: 16px; font-weight: 800; }
    .title a{ color: #0f172a; text-decoration: none; }
    .title a:hover{ text-decoration: underline; }
    .summary{ margin: 8px 0 0 0; font-size: 14px; color: rgba(15, 23, 42, 0.90); }
    .linkbtn{
      display: inline-block;
      margin-top: 10px;
      padding: 8px 10px;
      border-radius: 10px;
      border: 1px solid rgba(15, 23, 42, 0.12);
      background: rgba(255,255,255,0.92);
      color: #0f172a;
      text-decoration: none;
      font-weight: 700;
      font-size: 13px;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="panel">
      <div class="header">
        <div class="controls">
          <div class="control">
            <div class="label">Search</div>
            <input id="q" placeholder="Search updates" />
          </div>
          <div class="control small">
            <div class="label">Area</div>
            <select id="area"></select>
          </div>
          <div class="control small">
            <div class="label">Type</div>
            <select id="type"></select>
          </div>
          <div class="control btn">
            <div class="label">&nbsp;</div>
            <button id="reload" type="button">Reload</button>
          </div>
        </div>
        <div id="status" class="status">Loading updates...</div>
      </div>
      <div id="list" class="list"></div>
    </div>
  </div>

  <script>
    var FEED_URL = "https://raw.githubusercontent.com/PantsSlayer9000/News-Tracker/main/pinknews.json";

    function esc(s){
      return String(s || "").replace(/[&<>"']/g, function(c){
        return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c];
      });
    }

    function formatDateDMY(isoDate){
      if (!isoDate) return "Date not listed";
      var d = new Date(isoDate + "T00:00:00Z");
      if (isNaN(d.getTime())) return "Date not listed";
      return new Intl.DateTimeFormat("en-GB", { day:"2-digit", month:"long", year:"numeric" }).format(d);
    }

    function clean(s){
      return String(s || "").replace(/\s+/g, " ").trim();
    }

    var allItems = [];

    function buildDropdown(id, values, firstLabel){
      var sel = document.getElementById(id);
      sel.innerHTML = "";
      var opt0 = document.createElement("option");
      opt0.value = "";
      opt0.textContent = firstLabel;
      sel.appendChild(opt0);
      values.forEach(function(v){
        var o = document.createElement("option");
        o.value = v;
        o.textContent = v;
        sel.appendChild(o);
      });
    }

    function render(){
      var q = (document.getElementById("q").value || "").trim().toLowerCase();
      var area = document.getElementById("area").value;
      var type = document.getElementById("type").value;

      var filtered = allItems.filter(function(it){
        if (area && (it.area || "") !== area) return false;
        if (type && (it.label || "") !== type) return false;
        if (!q) return true;
        var t = ((it.title||"") + " " + (it.summary||"") + " " + (it.source||"") + " " + (it.area||"") + " " + (it.label||"")).toLowerCase();
        return t.indexOf(q) !== -1;
      });

      var status = document.getElementById("status");
      var list = document.getElementById("list");

      if (!allItems.length){
        status.textContent = "No updates yet.";
        list.innerHTML = "";
        return;
      }

      if (!filtered.length){
        status.textContent = "No matching updates.";
        list.innerHTML = "";
        return;
      }

      status.textContent = filtered.length + " update" + (filtered.length === 1 ? "" : "s") + " shown.";

      var out = "";
      var max = 40;

      for (var i = 0; i < filtered.length && i < max; i++){
        var it = filtered[i];
        var title = clean(it.title || "Untitled");
        var summary = clean(it.summary || "");
        var source = clean(it.source || "Source");
        var label = clean(it.label || "Update");
        var a = clean(it.area || "");
        var date = formatDateDMY(it.published);
        var url = it.url || "#";

        out += ""
          + "<div class='card'>"
          +   "<div class='meta'>"
          +     "<span class='pill'>" + esc(label) + "</span>"
          +     (a ? "<span class='pill'>" + esc(a) + "</span>" : "")
          +     "<span>" + esc(source) + "</span>"
          +     "<span>" + esc(date) + "</span>"
          +   "</div>"
          +   "<div class='title'><a href='" + esc(url) + "' target='_blank' rel='noopener'>" + esc(title) + "</a></div>"
          +   (summary ? "<div class='summary'>" + esc(summary) + "</div>" : "")
          +   "<a class='linkbtn' href='" + esc(url) + "' target='_blank' rel='noopener'>Open source</a>"
          + "</div>";
      }

      list.innerHTML = out;
    }

    function load(){
      document.getElementById("status").textContent = "Loading updates...";
      document.getElementById("list").innerHTML = "";

      fetch(FEED_URL + "?t=" + Date.now(), { cache: "no-store" })
        .then(function(r){ if(!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
        .then(function(items){
          allItems = Array.isArray(items) ? items : [];
          var areas = {};
          var types = {};

          allItems.forEach(function(it){
            if (it.area) areas[it.area] = true;
            if (it.label) types[it.label] = true;
          });

          buildDropdown("area", Object.keys(areas).sort(), "All areas");
          buildDropdown("type", Object.keys(types).sort(), "All types");

          render();
        })
        .catch(function(err){
          document.getElementById("status").textContent = "Could not load updates. " + (err && err.message ? err.message : "Unknown error");
        });
    }

    document.getElementById("q").addEventListener("input", render);
    document.getElementById("area").addEventListener("change", render);
    document.getElementById("type").addEventListener("change", render);
    document.getElementById("reload").addEventListener("click", load);

    load();
    setInterval(load, 30 * 60 * 1000);
  </script>
</body>
</html>
