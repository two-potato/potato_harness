"""Render a two-minute illustrated walkthrough from an actual report.

Optional authoring dependencies: Pillow and ffmpeg. This is paced explanatory
playback of recorded results, not a live screen capture or execution benchmark.
"""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import textwrap
from PIL import Image, ImageDraw, ImageFont


def render(report_path, destination, font_directory):
    report = json.loads(Path(report_path).read_text())
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    fonts = Path(font_directory)
    def font(size, bold=False):
        return ImageFont.truetype(str(fonts / ('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf')), size)
    chapters = [('Potato Harness', 'Доказательства вместо «готово»', [
        'Проверяемая автоматизация с AI-агентами.',
        'Один принятый результат. Три намеренных отказа.',
        'Реальные Git-коммиты, Python-тесты и SQLite.',
        'Этот пример — офлайн, без LLM и API-ключей.'])]
    explanations = [
        ['Ошибка: цена + количество вместо умножения.', 'Исполнитель меняет только разрешённый оператор.', 'Три теста проверяют обычную, пустую и одиночную корзину.'],
        ['Неверное предложение оставляет баг в коде.', 'Тесты действительно падают в отдельном процессе.', 'Заявление исполнителя не заменяет результат проверки.'],
        ['Тесты проходят, но отчёт ссылается на старый коммит.', 'Верификатор сравнивает SHA, задачу, ревизию и политику.', 'Старое доказательство не подтверждает новый результат.'],
        ['Координатор пытается записать изменение.', 'Операция запрещена до изменения файла.', 'Репозиторий остаётся на исходном коммите.']]
    titles = ['Исправление принято', 'Тесты не прошли', 'Доказательства устарели', 'Недостаточно полномочий']
    for item, notes, title in zip(report['scenarios'], explanations, titles):
        chapters.append((title, item['status'] + ' / ' + item['scenario'], notes + [
            'Измеренное время сценария: ' + str(item['elapsed_seconds']) + ' с.',
            'Ревизия задачи: ' + str(item['revision'])]))
    chapters.append(('Проверить самостоятельно', 'python3 tools/run_demo.py', [
        'HTML-отчёт + JSON-доказательства + журнал состояний.',
        'Ollama подключается отдельно: --adapter ollama --model …',
        'Это ограниченная демонстрация, не production sandbox.',
        'Адаптер модели проверен по HTTP-протоколу; live-запуск не заявлен.']))
    with tempfile.TemporaryDirectory() as tmp:
        frames = []
        for number, (title, subtitle, lines) in enumerate(chapters):
            im = Image.new('RGB', (1280, 720), '#101820')
            draw = ImageDraw.Draw(im)
            draw.text((64, 42), 'POTATO HARNESS  /  0.1.0-demo', font=font(20, True), fill='#f5b841')
            draw.text((64, 110), title, font=font(44, True), fill='#edf2f5')
            draw.text((64, 182), subtitle, font=font(25), fill='#9df3c2' if 'DONE' in subtitle else '#f5b841')
            y = 268
            for line in lines:
                for wrapped in textwrap.wrap(line, width=70):
                    draw.text((70, y), wrapped, font=font(25), fill='#c0d0da')
                    y += 39
                y += 14
            draw.line((64, 647, 1216, 647), fill='#344653', width=2)
            draw.text((64, 670), 'Иллюстрированный разбор реального отчёта · без звука', font=font(17), fill='#8fa6b4')
            draw.text((1145, 670), f'{number+1} / 6', font=font(17), fill='#8fa6b4')
            path = Path(tmp) / f'{number}.png'
            im.save(path)
            frames.append(path)
            if number == 0:
                im.save(destination / 'preview.png')
        playlist = Path(tmp) / 'frames.txt'
        playlist.write_text(''.join(f"file '{path}'\nduration 20\n" for path in frames) + f"file '{frames[-1]}'\n")
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(playlist),
                        '-t', '120', '-r', '10', '-c:v', 'libx264', '-preset', 'medium', '-crf', '28',
                        '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(destination / 'walkthrough.mp4')], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report')
    parser.add_argument('destination')
    parser.add_argument('--fonts', default='/usr/share/fonts/truetype/dejavu')
    args = parser.parse_args()
    render(args.report, args.destination, args.fonts)
