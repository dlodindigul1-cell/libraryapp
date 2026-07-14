# நூலகர் விடுப்பு மேலாண்மை — Flask பதிப்பு (Setup Guide)

இது Google Apps Script "விடுப்பு பதிவு" app-ன் Flask + Service Account
பதிப்பு. இதனால் **மொபைலில் multiple Google account login பிரச்சனை
முழுசா தீரும்** — browser-ல் Google login தேவையே இல்லை.

## கோப்பு அமைப்பு

```
leave-app/
├── app.py                  ← Flask routes (/leave, /leave/api/<fn>)
├── sheets_service.py        ← Google Sheets read/write logic (Code.gs-ன் port)
├── pdf_service.py           ← PDF உருவாக்கம் (HTML → PDF)
├── drive_service.py         ← Google Drive-ல் PDF upload
├── templates/leave_index.html  ← அதே பழைய frontend (shim மட்டும் add ஆனது)
├── static/gas-shim.js       ← google.script.run-ஐ fetch()-ஆக மாற்றும் shim
├── requirements.txt
└── Procfile
```

## படி 1 — Google Cloud Console-ல் Service Account உருவாக்குதல்

1. https://console.cloud.google.com -ல் ஒரு project உருவாக்குங்க (அல்லது
   ஏற்கனவே ஒன்று இருந்தா அதையே பயன்படுத்தலாம்).
2. **APIs & Services → Library**-ல் இவற்றை Enable பண்ணுங்க:
   - **Google Sheets API**
   - **Google Drive API**
3. **APIs & Services → Credentials → Create Credentials → Service Account**
   - பெயர்: எ.கா `library-portal-bot`
   - "Done" க்ளிக் பண்ணுங்க (role தேவையில்லை, sheet/folder level-லேயே share பண்ணுவோம்)
4. உருவான Service Account-ஐ க்ளிக் பண்ணி, **Keys → Add Key → Create new key
   → JSON** தேர்ந்தெடுங்க. ஒரு `.json` file download ஆகும் — இதை பத்திரமா
   வையுங்க (இது ஒரு password போன்றது, யாருக்கும் பகிர வேண்டாம்).
5. அந்த JSON file-ல் `"client_email"` என்ற field-ல் ஒரு email இருக்கும்
   (எ.கா `library-portal-bot@your-project.iam.gserviceaccount.com`) —
   இதைத்தான் அடுத்த படியில் sheet/folder-ஐ share பண்ண பயன்படுத்துவோம்.

## படி 2 — Sheet மற்றும் Drive Folder-ஐ Service Account-க்கு Share பண்ணுதல்

1. உங்க "நூலகர் விடுப்பு மேலாண்மை" Google Sheet-ஐ திறந்து **Share** பண்ணி,
   மேலே கிடைத்த `client_email`-ஐ **Editor** ஆக add பண்ணுங்க.
2. `DRIVE_FOLDER_ID = 1T_uEVBJgQdDIS_OgLkAWOpUKOhGrbk6K` — இந்த Drive
   folder-ஐயும் அதே `client_email`-க்கு **Editor** ஆக share பண்ணுங்க
   (PDF இங்குதான் சேமிக்கப்படும்).

## படி 3 — Environment Variables (Render-ல் Set பண்ண வேண்டியவை)

| Key | Value |
|---|---|
| `SPREADSHEET_ID` | `1ZQBs6Hnbh0H_lMJ0m38w_5HjwWOCTEoDN9Oo-44DtSQ` |
| `SHEET_NAME_ENTRY` | `LEAVE_ENTRY` |
| `SHEET_NAME_MASTER` | `MASTER` *(உங்க sheet-ல் இந்தப் பெயர் இல்லைன்னா மாத்துங்க)* |
| `SHEET_NAME_RH` | `RH DATES` *(வேற பெயரா இருந்தா மாத்துங்க)* |
| `DRIVE_FOLDER_ID` | `1T_uEVBJgQdDIS_OgLkAWOpUKOhGrbk6K` |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Step1-ல் download பண்ண .json file-ன் **முழு content-ஐயும்** ஒரே வரியா copy-paste பண்ணுங்க |

⚠️ `GOOGLE_SERVICE_ACCOUNT_JSON`-ஐ Render dashboard-ல் "Environment"
tab-ல் ஒரு secret variable-ஆ சேர்க்கணும் — code-ல் ஒருபோதும் hardcode
பண்ணக்கூடாது, git-ல் commit பண்ணக்கூடாது.

## படி 4 — Render-ல் Deploy பண்ணுதல்

1. இந்த `leave-app/` folder-ஐ உங்க existing git repo-ல் (portal இருக்கிற
   repo) ஒரு subfolder-ஆ சேருங்க, அல்லது தனி repo-ஆ உருவாக்குங்க.
2. Render-ல் **New → Web Service** → repo-ஐ connect பண்ணுங்க.
3. Settings:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
   - Root Directory: `leave-app` (subfolder-ஆ வெச்சிருந்தா)
4. மேலே சொன்ன Environment Variables-ஐ சேருங்க.
5. Deploy பண்ணுங்க. முடிஞ்சதும் உங்க app இப்படி இருக்கும்:
   `https://your-service.onrender.com/leave`

## படி 5 — Portal-ல் Link மாற்றுதல்

Portal-ன் `index.html`-ல் இருக்கிற:
```js
leave: "https://script.google.com/macros/s/AKfycbw.../exec"
```
என்பதை:
```js
leave: "https://your-service.onrender.com/leave"
```
என மாற்றுங்க (இரண்டு apps-ஐயும் ஒரே Render service-ல் host பண்ணினா,
relative path `/leave` போதும்).

## Local-ல் Test பண்ண

```bash
cd leave-app
pip install -r requirements.txt
export SPREADSHEET_ID="1ZQBs6Hnbh0H_lMJ0m38w_5HjwWOCTEoDN9Oo-44DtSQ"
export SHEET_NAME_ENTRY="LEAVE_ENTRY"
export DRIVE_FOLDER_ID="1T_uEVBJgQdDIS_OgLkAWOpUKOhGrbk6K"
export GOOGLE_SERVICE_ACCOUNT_JSON="$(cat /path/to/service-account.json)"
python app.py
# http://localhost:5000/leave
```

## கவனிக்க வேண்டியவை

- **MASTER sheet column order**: Col B=நூலகம், C=நூலகர் எண், D=நூலகர்
  பெயர், E=வகை, G=மெயில் — Code.gs-ல் இருந்ததே அப்படியே port
  செய்யப்பட்டுள்ளது. உங்க sheet-ல் column order வேற மாதிரி இருந்தா
  `sheets_service.py`-ல் `get_all_employees()` function-ல் index
  எண்களை மாத்தணும்.
- **Email அனுப்புதல் தற்போது இல்லை** (உங்க தேர்வுப்படி) — PDF உருவான
  உடனே Drive link-ஆ screen-ல் காட்டப்படும். பின்னாடி வேணும்னா Gmail
  SMTP/API சேர்க்கலாம்.
- **PDF வடிவமைப்பு**: `xhtml2pdf` பயன்படுத்தப்பட்டுள்ளது (எளிதான Render
  deploy-க்காக, system-level libraries தேவையில்லை). Layout சிறிது
  simple-ஆ இருக்கும் — Tamil font correctly render ஆக வேண்டும் எனில்,
  Render build-ல் Noto Sans Tamil `.ttf` font file-ஐ சேர்த்து
  xhtml2pdf-க்கு register பண்ண வேண்டியிருக்கலாம் (தேவைப்பட்டா அடுத்த
  step-ல் சேர்ப்போம்).
