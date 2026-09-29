"""Hedef hareket modeli — Kalman filtresi.

Her iz icin konum ve hizi tahmin eder. Iki kullanim amaci vardir:

1. Tespitler arasi konum tahmini. Cikarim ~10 Hz, kontrol dongusu 50 Hz
   calisir; aradaki surede hedefin nerede oldugu tahmin edilir.

2. Kisa sureli kayipta izin yasatilmasi. Tespit gelmese bile tahmin
   surer; angajman katmani bu tahmini kullanarak hedefi yeniden
   eslestirebilir.

Durum vektoru: [x, y, vx, vy]
    x, y    Kutu merkezi (piksel)
    vx, vy  Hiz (piksel/saniye)

Sabit hiz modeli kullanilir. Ivme terimi eklenmemistir; hava
hedefleri icin sabit hiz varsayimi daha kararli sonuc verir.
"""

import numpy as np

from config import settings


class MotionModel:
    """Tek bir izin konum ve hizini tahmin eden Kalman filtresi."""

    def __init__(self, x, y, timestamp):
        """Filtreyi ilk olcumle baslatir.

        Args:
            x: Baslangic x konumu (piksel)
            y: Baslangic y konumu (piksel)
            timestamp: Olcum zamani (saniye)
        """
        self.state = np.array([x, y, 0.0, 0.0], dtype=np.float64)

        # Kovaryans — baslangicta konum bilinir, hiz bilinmez
        self.covariance = np.diag([
            settings.KF_INIT_POS_VAR,
            settings.KF_INIT_POS_VAR,
            settings.KF_INIT_VEL_VAR,
            settings.KF_INIT_VEL_VAR,
        ]).astype(np.float64)

        self.last_update = timestamp
        self.last_predict = timestamp

    def predict(self, timestamp):
        """Durumu verilen zamana ilerletir.

        Olcum olmadan yalnizca modele dayanarak tahmin yapar.
        Belirsizlik her cagrida artar.

        Args:
            timestamp: Hedef zaman (saniye)

        Returns:
            (x, y, vx, vy) — tahmin edilen durum
        """
        dt = timestamp - self.last_predict

        if dt <= 0:
            return self.as_tuple()

        f = self._transition_matrix(dt)
        q = self._process_noise(dt)

        self.state = f @ self.state
        self.covariance = f @ self.covariance @ f.T + q

        self.last_predict = timestamp
        return self.as_tuple()

    def update(self, x, y, timestamp):
        """Olcumle durumu duzeltir.

        Args:
            x: Olculen x konumu (piksel)
            y: Olculen y konumu (piksel)
            timestamp: Olcum zamani (saniye)

        Returns:
            (x, y, vx, vy) — duzeltilmis durum
        """
        self.predict(timestamp)

        # Olcum matrisi: yalnizca konum olculur, hiz olculmez
        h = np.array([
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
        ], dtype=np.float64)

        r = np.diag([
            settings.KF_MEAS_VAR,
            settings.KF_MEAS_VAR,
        ]).astype(np.float64)

        measurement = np.array([x, y], dtype=np.float64)
        innovation = measurement - h @ self.state

        s = h @ self.covariance @ h.T + r
        kalman_gain = self.covariance @ h.T @ np.linalg.inv(s)

        self.state = self.state + kalman_gain @ innovation

        identity = np.eye(4, dtype=np.float64)
        self.covariance = (identity - kalman_gain @ h) @ self.covariance

        self.last_update = timestamp
        return self.as_tuple()

    def position_uncertainty(self):
        """Konum belirsizliginin buyuklugunu dondurur.

        Yeniden eslestirmede arama yaricapi olarak kullanilir.

        Returns:
            float — standart sapma (piksel)
        """
        return float(np.sqrt(self.covariance[0, 0] + self.covariance[1, 1]))

    def as_tuple(self):
        """Durumu demet olarak dondurur.

        Returns:
            (x, y, vx, vy)
        """
        return (float(self.state[0]), float(self.state[1]),
                float(self.state[2]), float(self.state[3]))

    @staticmethod
    def _transition_matrix(dt):
        """Sabit hiz gecis matrisini uretir.

        x_yeni = x + vx * dt
        v_yeni = v

        Args:
            dt: Gecen sure (saniye)

        Returns:
            4x4 NumPy dizisi
        """
        return np.array([
            [1.0, 0.0, dt,  0.0],
            [0.0, 1.0, 0.0, dt ],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ], dtype=np.float64)

    @staticmethod
    def _process_noise(dt):
        """Surec gurultusu matrisini uretir.

        Sabit ivme gurultusu modeli: hedefin modelden sapma egilimini
        temsil eder. Manevra yapan hedeflerde yuksek deger gerekir.

        Args:
            dt: Gecen sure (saniye)

        Returns:
            4x4 NumPy dizisi
        """
        sigma = settings.KF_PROCESS_NOISE
        dt2 = dt * dt
        dt3 = dt2 * dt
        dt4 = dt2 * dt2

        q_pos = dt4 / 4.0 * sigma
        q_pos_vel = dt3 / 2.0 * sigma
        q_vel = dt2 * sigma

        return np.array([
            [q_pos,     0.0,       q_pos_vel, 0.0      ],
            [0.0,       q_pos,     0.0,       q_pos_vel],
            [q_pos_vel, 0.0,       q_vel,     0.0      ],
            [0.0,       q_pos_vel, 0.0,       q_vel    ],
        ], dtype=np.float64)