import { useEffect, useRef, useState } from "react";
import { GoogleTrafficMap } from "./GoogleTrafficMap";
import type { Position } from "./google";
import type { MapFeature } from "./model";

export function JourneyMap({ features, onSelect }: { features: MapFeature[]; onSelect: (id: string) => void }) {
  const [origin, setOrigin] = useState<Position>();
  const [destination, setDestination] = useState<Position>();
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
  const [denied, setDenied] = useState(false);
  const request = useRef(0);
  useEffect(() => () => { request.current++; }, []);
  function locate() {
    const id = ++request.current;
    if (!navigator.geolocation) { setMessage("تحديد الموقع غير متاح في هذا المتصفح. افتح الصفحة في Chrome أو Safari وفعّل خدمات الموقع للجهاز."); return; }
    setPending(true); setDenied(false); setMessage("");
    navigator.geolocation.getCurrentPosition(position => {
      if (id !== request.current) return;
      setOrigin({ lat: position.coords.latitude, lng: position.coords.longitude });
      setDestination(undefined); setPending(false); setDenied(false);
      setMessage(`دقة الموقع التقريبية: ${Math.round(position.coords.accuracy)} متر. حدد وجهتك بالنقر على الخريطة.`);
    }, error => {
      if (id !== request.current) return;
      setPending(false); setDenied(error.code === 1);
      setMessage(error.code === 1 ? "الوصول لموقع الجهاز محظور. اسمح بالموقع من إعدادات المتصفح ثم أعد المحاولة." : "تعذر الحصول على موقع الجهاز. تأكد من تشغيل خدمات الموقع والاتصال بالإنترنت، ثم أعد المحاولة.");
    }, { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 });
  }
  return <div className="journey-map">
    <section className="map-detail" dir="rtl" aria-label="الموقع والوجهة">
      <h2>{origin ? "إلى أين تريد الذهاب؟" : "حدد موقعك من الجهاز"}</h2>
      <p>شارك موقعك لفتح الخريطة حولك، ثم حدد وجهتك. موقع البداية والوجهة يبقيان في هذه الصفحة ولا يُحفظان في حسابك. عرض الموقع على الخريطة يستخدم Google Maps.</p>
      <button disabled={pending} onClick={locate}>{pending ? "جارٍ تحديد موقعك…" : origin ? "تحديث موقعي" : "تحديد موقعي من الجهاز"}</button>
      {message && <p role="status">{message}</p>}
      {denied && <div className="location-help">
        <h3>السماح باستخدام الموقع</h3>
        <ol>
          <li>اضغط أيقونة إعدادات الموقع بجانب عنوان الصفحة في المتصفح.</li>
          <li>افتح أذونات الموقع واختر «السماح» للموقع الجغرافي.</li>
          <li>إذا بقي محظورًا، فعّل خدمات الموقع للمتصفح من إعدادات الخصوصية في جهازك.</li>
        </ol>
        <p>بعد السماح، اضغط «تحديد موقعي من الجهاز» مجددًا. لا يستطيع النظام تجاوز رفض الإذن.</p>
      </div>}
      {origin && <p>تم تحديد نقطة البداية من موقع جهازك.</p>}
      {origin && !destination && <p>اضغط على مكان وجهتك في الخريطة أدناه.</p>}
      {destination && <p>تم تحديد وجهتك على الخريطة. <button onClick={() => setDestination(undefined)}>تغيير الوجهة</button></p>}
      {destination && <p>تم تحديد الوجهة فقط؛ حساب المسار وإرشادات الملاحة غير مفعّلين بعد.</p>}
    </section>
    {origin && <GoogleTrafficMap features={features} onSelect={onSelect} origin={origin} destination={destination} onPick={setDestination} />}
  </div>;
}
