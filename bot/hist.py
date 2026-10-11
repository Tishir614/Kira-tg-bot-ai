from typing import Any

from unidecode import unidecode

import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import io


def create_hist_penis(data: list, title: str = 'Самые длинные члены в чате!', color: str = 'YlOrRd') -> bytes:
	# 1. Лёгкий тёмный стиль, без лишней сетки
	sns.set_theme(style="darkgrid", rc={"axes.grid": False})  # сетка только по y

	# Данные
	names = [fix_names(item.name) for item in data]
	penis = [round(item.leng, 2) for item in data]
	df = pd.DataFrame({'Имя': names, 'Длина': penis})
	df = df.sort_values('Длина', ascending=False).reset_index(drop=True)

	# 2. Фон и цвета
	fig, ax = plt.subplots(figsize=(10, 6))
	fig.patch.set_facecolor('#0e0e0e')        # тёмно‑чёрный фон
	ax.set_facecolor('#151515')               # чуть светлее внутри area

	v_min, v_max = df['Длина'].min(), df['Длина'].max()
	if v_min == v_max:
		v_min -= 1

	norm = plt.Normalize(v_min, v_max)
	cmap = plt.cm.get_cmap(color)
	colors = [cmap(norm(val)) for val in df['Длина']]

	# 3. Бары — более плоские и без серых рамок
	barplot = sns.barplot(
		data=df,
		x='Имя',
		y='Длина',
		ax=ax,
		hue='Имя',
		palette=colors,
		alpha=0.9,
		edgecolor="none",
		linewidth=0,
		legend=False
	)

	# 4. Сетка только по y, очень тонкая
	ax.yaxis.grid(True, linestyle="--", alpha=0.2, color="#666666")
	ax.set_axisbelow(True)

	# 5. Текст — современный, светлый
	ax.set_title(
		title,
		fontsize=20,
		color="white",
		pad=20,
		fontweight="bold",
		family="sans-serif"
	)

	ax.set_xlabel("", color="white")
	ax.set_ylabel(
		"Сантиметры",
		fontsize=12,
		color="#aaaaaa",
		family="sans-serif"
	)

	ax.tick_params(axis='x', rotation=25, colors='#dddddd', labelsize=11)
	ax.tick_params(axis='y', colors='#dddddd', labelsize=10)

	# Убираем рамку вокруг графика
	for spine in ax.spines.values():
		spine.set_visible(False)

	# 6. Цифры чуть выше столбиков
	bar_heights = [p.get_height() for p in barplot.patches]
	max_h = max(bar_heights) if bar_heights else 1
	offset = max_h * 0.03  # относительный отступ

	for p, c in zip(barplot.patches, colors):
		h = p.get_height()
		ax.annotate(
			f"{h:.1f}",
			(p.get_x() + p.get_width() / 2.0, h + offset),
			ha="center",
			va="bottom",
			fontsize=11,
			fontweight="bold",
			color="white",
			family="monospace"
		)

	plt.tight_layout(pad=1.5)

	# 7. Сохранение в байты
	buf = io.BytesIO()
	plt.savefig(
		buf,
		format="png",
		facecolor=fig.get_facecolor(),
		edgecolor="none",
		dpi=160,
		bbox_inches="tight",
		transparent=False
	)
	plt.close(fig)

	return buf.getvalue()

def create_chart_messages(data: list[Any]) -> bytes:
	names = [fix_names(item.name) for item in data]
	messages = [item.leng for item in data]

	plt.figure(figsize=(12, 6))
	bars = plt.bar(names, messages, color='skyblue')
	plt.ylabel('Сообщений написано')
	plt.title('Топ чата')
	plt.xticks(rotation=15, ha='right')
	plt.tight_layout()

	for bar, msg_count in zip(bars, messages):
		plt.text(bar.get_x() + bar.get_width()/2, bar.get_height(), str(msg_count), ha='center', va='bottom')

	buf = io.BytesIO()
	plt.savefig(buf, format='png')
	buf.name = 'chart.png'
	buf.seek(0)
	plt.close()
	return buf.getvalue()

def fix_names(text: str) -> str:
	result = []
	for ch in text:
		if 'А' <= ch <= 'я' or ch == 'Ё' or ch == 'ё':
			result.append(ch)
		else:
			result.append(unidecode(ch))
	return ''.join(result)
