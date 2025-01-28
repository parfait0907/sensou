import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
import os
from dotenv import load_dotenv
from keep_alive import keep_alive
load_dotenv()
# Botの設定
intents = discord.Intents.default()  # デフォルトのインテント（Botがアクセス可能なイベントやデータ）
intents.message_content = True  # メッセージの内容にアクセスする権限を付与
bot = commands.Bot(command_prefix="/", intents=intents)  # Botインスタンスの作成。プレフィックスは「/」

# ゲームの状態管理
players = []          # 参加プレイヤーのリスト
deck = []             # トランプデッキ（全カード）
hands = {}            # 各プレイヤーの手札を記録する辞書
points = {}           # 各プレイヤーのスコアを記録する辞書
played_cards = {}     # プレイヤーが出したカードを記録する辞書
card_stack = []       # 場に出されたカードを保持するスタック
tie_count = 0         # 引き分けの回数をカウント
carry_over_cards = [] # 引き分け時に蓄積されるカード
last_victory_message = None  # 最新の勝利メッセージを保存する変数

# グローバルロック
compare_cards_lock = asyncio.Lock()



# 絵文字マッピング
suit_emojis = {  # スート（マーク）を対応する絵文字に変換
    '♥': '❤️',
    '♦': '♦️',
    '♠': '♠️',
    '♣': '♣️'
}
value_emojis = {  # カードの値を対応する絵文字に変換
    2: '2️⃣', 3: '3️⃣', 4: '4️⃣', 5: '5️⃣', 6: '6️⃣', 7: '7️⃣', 8: '8️⃣', 9: '9️⃣', 10: '🔟',
    11: 'J', 12: 'Q', 13: 'K', 14: 'A'
}

#    Botが起動した際に実行されるイベントハンドラー。Botのログイン情報を出力し、スラッシュコマンドを同期する。
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')  # Botのユーザー名をコンソールに表示
    try:
        synced = await bot.tree.sync()  # スラッシュコマンドを同期
        print(f"Synced {len(synced)} command(s)")  # 同期されたコマンド数を出力
    except Exception as e:
        print(e)  # エラー内容を出力


# メインメニューのスラッシュコマンド
@bot.tree.command(name="メインメニュー", description="メインメニューを表示します")
async def main_menu(interaction: discord.Interaction):

    #Viewオブジェクト（ボタン付きのUI）を送信。

    MainMenu_view = MainMenuView()  # メインメニュー用のViewオブジェクト

    await interaction.response.send_message(
        content="コマンドを選択してください:", 
        view=MainMenu_view, 
        ephemeral=True
    )  # Ephemeral=True: メッセージはコマンド実行者のみに表示





"""
@bot.tree.command(name="メインメニュー", description="メインメニューを表示します")
async def main_menu(interaction: discord.Interaction):


    # Embedメッセージの生成
    embed = discord.Embed(
        title="メインメニュー",
        description="以下のボタンから操作を選択してください。",
        color=discord.Color.blue()
    )
    embed.add_field(name="戦争ゲーム募集", value="ゲームを新規に開始する場合に選択してください。", inline=False)
    embed.add_field(name="参加", value="既存のゲームに参加します。", inline=False)
    embed.add_field(name="ゲームを開始", value="ゲームを開始します（プレイヤー人数要件を満たしている場合）。", inline=False)
    embed.add_field(name="手札を引く", value="カードを引いて手札を選択します。", inline=False)
    embed.add_field(name="確認", value="現在のゲーム状態を確認します。", inline=False)

    # Viewオブジェクト（ボタン付きのUI）を送信
    MainMenu_view = MainMenuView()  # メインメニュー用のViewオブジェクト
    await interaction.response.send_message(
        embed=embed,  # Embedメッセージを送信
        view=MainMenu_view,  # ボタンView
        ephemeral=True  # メッセージはコマンド実行者のみに表示
    )
"""


# デッキ初期化
def initialize_deck():

    #トランプデッキを初期化し、シャッフルする。

    global deck
    suits = ['♥', '♦', '♠', '♣']  # トランプのスート（マーク）
    values = list(range(2, 15))  # カードの値（2〜14）。Aceは14
    deck = [(suit, value) for suit in suits for value in values]  # デッキを生成（全52枚）
    random.shuffle(deck)  # デッキをシャッフル

# デッキ配分
def distribute_deck():

    #プレイヤー人数に応じてデッキを配分する。
    #2人の場合は赤（♥, ♦）と黒（♠, ♣）に分ける。
    #4人の場合は均等に4分割。

    global deck
    if len(players) == 2:
        # 2人用: 赤と黒で分割
        red_deck = [card for card in deck if card[0] in ['♥', '♦']]
        black_deck = [card for card in deck if card[0] in ['♠', '♣']]
        deck = red_deck + black_deck
    elif len(players) == 4:
        # 4人用: 均等に分配
        deck = [deck[i::4] for i in range(4)]  # 各4分割
        deck = sum(deck, [])  # フラットに変換（リストを結合）

# カードを絵文字で表示
def card_to_emoji(card):

    #カードを対応する絵文字に変換する。

    suit, value = card  # カードはタプル形式 (スート, 値)
    return f"{suit_emojis[suit]}{value_emojis[value]}"  # スートと値を対応する絵文字に変換


# メインメニューのView（UIの定義）
class MainMenuView(discord.ui.View):
    def __init__(self):
        super().__init__()
        # 「戦争ゲーム募集」ボタンを作成
        self.add_item(discord.ui.Button(label="戦争ゲーム募集", style=discord.ButtonStyle.primary, custom_id="recruit"))
        # 「参加」ボタンを作成
        #self.add_item(discord.ui.Button(label="参加", style=discord.ButtonStyle.success, custom_id="join"))
        # 「ゲームを開始」ボタンを作成
        self.add_item(discord.ui.Button(label="ゲームを開始", style=discord.ButtonStyle.secondary, custom_id="start_game"))
        # 「手札を引く」ボタンを作成
        self.add_item(discord.ui.Button(label="手札を引く", style=discord.ButtonStyle.danger, custom_id="draw_hand"))
        # （オプション）確認ボタン
        #self.add_item(discord.ui.Button(label="確認", style=discord.ButtonStyle.danger, custom_id="check_status"))

    # すべてのユーザーにボタン操作を許可
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return True

    # タイムアウト時の特別な処理は未定義
    async def on_timeout(self):
        pass



# カードを出した時のView
class selectView(discord.ui.View):
    def __init__(self):
        super().__init__()

        # 「手札を引く」ボタンを作成
        self.add_item(discord.ui.Button(label="手札を引く", style=discord.ButtonStyle.danger, custom_id="draw_hand"))
        # （オプション）確認ボタン
        self.add_item(discord.ui.Button(label="確認", style=discord.ButtonStyle.danger, custom_id="check_status"))




# 手札選択ボタンのView
class HandView(discord.ui.View):
    def __init__(self, player):
        

        #プレイヤーが手札を選択できるUI（ボタン）を提供するView。

        super().__init__(timeout=None)  # タイムアウト時間を設定

        self.add_item(discord.ui.Button(label="確認", style=discord.ButtonStyle.danger, custom_id="check_status"))
        self.add_item(discord.ui.Button(label="手札を引く", style=discord.ButtonStyle.danger, custom_id="draw_hand"))


        self.player = player  # このViewを管理するプレイヤー

        # 手札に基づいてボタンを作成
        for index, card in enumerate(hands[player]):
            button = discord.ui.Button(
                label=card_to_emoji(card),  # カードの絵文字をボタンラベルとして表示
                style=discord.ButtonStyle.primary  # プライマリ（青色）スタイルのボタン
            )
            button.callback = self.create_callback(card, index)  # ボタンに対応するコールバックを設定
            self.add_item(button)  # ボタンをViewに追加
            

    async def on_timeout(self):

        #Viewのタイムアウトが発生した場合に呼び出されるメソッド。

        print("HandViewがタイムアウトしました。ボタンは無効です。")  # タイムアウトをログに記録

    def create_callback(self, card, index):
        async def callback(interaction: discord.Interaction):
            if interaction.user != self.player:  # ボタンを押したのが別のユーザーの場合
                await interaction.response.send_message("これはあなたの手札ではありません。", ephemeral=True)
                return

            if interaction.user in played_cards:  # 既にカードを出した場合
                await interaction.response.send_message("すでにカードを出しています。他のプレイヤーのターンをお待ちください。", ephemeral=True)
                return

            # プレイヤーが選択したカードを処理
            selected_card = hands[self.player].pop(index)  # 手札から選択したカードを削除
            played_cards[self.player] = selected_card  # プレイヤーの出したカードを記録

            select_View = selectView()

            await interaction.response.edit_message(
                content=f"あなたは {card_to_emoji(selected_card)} を出しました！", 
                view=select_View
            )

            if len(played_cards) == len(players):  # 全プレイヤーがカードを出し終えた場合
                await compare_cards(interaction.channel)  # 勝敗判定を実行

            if deck:  # デッキにカードが残っている場合
                hands[self.player].append(deck.pop())  # デッキから新しいカードを手札に追加

        return callback



# カードの勝敗判定
async def compare_cards(channel):  
    global tie_count, card_stack, played_cards, last_victory_message, carryover_points

    # キャリーオーバーポイントの初期化
    carryover_points = carryover_points if 'carryover_points' in globals() else 0

    async with compare_cards_lock:
        if len(played_cards) < len(players):
            return  # 全員がカードを出すまで待機

        card_stack.extend(played_cards.values())  # 出されたカードをスタックに追加

        # 特別ルール: Aと2が同時に場に出ている場合
        twos = [player for player, card in played_cards.items() if card[1] == 2]
        aces = [player for player, card in played_cards.items() if card[1] == 14]

        if twos and aces:
            if len(twos) == 1:
                winner = twos[0]
                round_points = len(card_stack) + carryover_points  # キャリーオーバーポイントを加算
                points[winner] += round_points

                embed = discord.Embed(
                    title="特別ルール適用: 勝者決定！",
                    description=f"**{winner.name}** さんが勝利しました！",
                    color=discord.Color.gold()
                )

                # 各プレイヤーが出したカードを追加
                for player, card in played_cards.items():
                    embed.add_field(
                        name=f"{player.name} さんが出したカード",
                        value=f"{card_to_emoji(card)}",
                        inline=False
                    )

                # 全プレイヤーのスコアを表示
                score_details = "\n".join([f"{player.name}: {points[player]} 点" for player in players])
                embed.add_field(
                    name="現在のスコア",
                    value=score_details,
                    inline=False
                )

                embed.add_field(name="獲得ポイント", value=f"**{round_points}**", inline=False)
                embed.add_field(name="累計ポイント", value=f"**{points[winner]}**", inline=False)

                if last_victory_message:
                    await last_victory_message.edit(embed=embed)
                else:
                    last_victory_message = await channel.send(embed=embed)

                carryover_points = 0  # キャリーオーバーをリセット
                card_stack.clear()
            else:
                tie_count += 1
                carryover_points += len(card_stack)  # 引き分け時にスタックポイントをキャリーオーバー

                embed = discord.Embed(
                    title="特別ルール適用: 引き分け",
                    description="カードは次の勝者が獲得します。",
                    color=discord.Color.blue()
                )

                # 各プレイヤーが出したカードを追加
                for player, card in played_cards.items():
                    embed.add_field(
                        name=f"{player.name} さんが出したカード",
                        value=f"{card_to_emoji(card)}",
                        inline=False
                    )

                # 全プレイヤーのスコアを表示
                score_details = "\n".join([f"{player.name}: {points[player]} 点" for player in players])
                embed.add_field(
                    name="現在のスコア",
                    value=score_details,
                    inline=False
                )


                if last_victory_message:
                    await last_victory_message.edit(embed=embed)
                else:
                    last_victory_message = await channel.send(embed=embed)

            played_cards.clear()
            return

        # 通常ルール
        max_value = max(card[1] for card in card_stack)
        strongest_players = [
            player for player, card in played_cards.items() if card[1] == max_value
        ]

        if len(strongest_players) > 1:
            tie_count += 1
            carryover_points += len(card_stack)  # 引き分け時にスタックポイントをキャリーオーバー

            embed = discord.Embed(
                title="引き分け",
                description="カードは次の勝者が獲得します。",
                color=discord.Color.blue()
            )

            # 各プレイヤーが出したカードを追加
            for player, card in played_cards.items():
                embed.add_field(
                    name=f"{player.name} さんが出したカード",
                    value=f"{card_to_emoji(card)}",
                    inline=False
                )

            # 全プレイヤーのスコアを表示
            score_details = "\n".join([f"{player.name}: {points[player]} 点" for player in players])
            embed.add_field(
                name="現在のスコア",
                value=score_details,
                inline=False
            )
        
            

            if last_victory_message:
                await last_victory_message.edit(embed=embed)
            else:
                last_victory_message = await channel.send(embed=embed)
        else:
            winner = strongest_players[0]
            round_points = len(card_stack) + carryover_points  # キャリーオーバーポイントを加算
            points[winner] += round_points

            embed = discord.Embed(
                title="ラウンド勝利",
                description=f"**{winner.name}** さんがこのラウンドで勝利しました！",
                color=discord.Color.green()
            )

            # 各プレイヤーが出したカードを追加
            for player, card in played_cards.items():
                embed.add_field(
                    name=f"{player.name} さんが出したカード",
                    value=f"{card_to_emoji(card)}",
                    inline=False
                )

            # 全プレイヤーのスコアを表示
            score_details = "\n".join([f"{player.name}: {points[player]} 点" for player in players])
            embed.add_field(
                name="現在のスコア",
                value=score_details,
                inline=False
            )

            # 獲得ポイントと累計ポイントを追加
            embed.add_field(name="獲得ポイント", value=f"**{round_points}**", inline=False)
            embed.add_field(name="累計ポイント", value=f"**{points[winner]}**", inline=False)

            # メッセージの送信または更新
            if last_victory_message:
                await last_victory_message.edit(embed=embed)
            else:
                last_victory_message = await channel.send(embed=embed)


            carryover_points = 0  # キャリーオーバーをリセット

        card_stack.clear()
        played_cards.clear()
        await handle_round_end(channel)



#ここから削除



#ここまで



# ボタンのインタラクション処理
@bot.event
async def on_interaction(interaction: discord.Interaction):

    global deletemessage

    # ボタンのクリック（インタラクション）の種類を確認
    if interaction.type == discord.InteractionType.component:
        # クリックされたボタンのカスタムIDを取得
        custom_id = interaction.data.get("custom_id")

        # 各ボタンに対応する処理を呼び出し
        if custom_id == "recruit":  # ゲーム募集
            await handle_recruit(interaction)
        elif custom_id == "join":  # ゲームへの参加
            await handle_join(interaction)
        elif custom_id == "start_game":  # ゲーム開始
            await handle_start_game(interaction)
        elif custom_id == "draw_hand":  # 手札を引く

            #await deletemessage.delete()

            player = interaction.user

            if player not in hands:  # 手札を持っているか確認
                await interaction.response.send_message("あなたはこのゲームに参加していません。", ephemeral=True)
                return

            if hands[player]:  # 手札がある場合
                Hand_view = HandView(player)  # 新しいViewを作成
                await interaction.response.edit_message(
                    content="カードを一枚選んでください:",  # メッセージを更新
                    view=Hand_view
                )

            else:
                # 手札が空の場合
                await interaction.response.send_message(content="現在、手札がありません。", ephemeral=True)
        
            #await handle_show_hand(interaction)
        elif custom_id == "check_status":  # 確認
            await handle_check_status(interaction)



# 戦争ゲーム募集を開始する処理
async def handle_recruit(interaction: discord.Interaction):
    global players, points, hands, deck, played_cards, card_stack, tie_count, carry_over_cards, last_victory_message

    # ゲーム状態をリセット
    players = []
    points = {}
    hands = {}
    deck = []
    played_cards = {}
    card_stack = []
    tie_count = 0
    carry_over_cards = []
    last_victory_message = None

    # 募集メッセージを送信し、メッセージを記憶
    message = await interaction.channel.send(
        content="戦争ゲームの募集を開始しました！参加するには「参加」ボタンを押してください。",
        view=RecruitView()  # 新しいViewを使用
    )
    last_victory_message = message  # 募集メッセージを記録



class RecruitView(discord.ui.View):
    def __init__(self):
        super().__init__()

        # 参加ボタンを追加
        self.add_item(discord.ui.Button(label="参加", style=discord.ButtonStyle.success, custom_id="join"))



# ゲームへの参加処理
async def handle_join(interaction: discord.Interaction):
    if interaction.user in players:
        # 既に参加している場合
        await interaction.response.edit_message(content=f"{interaction.user.name}さん、既に参加しています。")
    else:
        # プレイヤーリストに追加
        players.append(interaction.user)
        await interaction.response.edit_message(content=f"{interaction.user.name}さんがゲームに参加しました！")


# ゲーム開始処理
async def handle_start_game(interaction: discord.Interaction):
    if len(players) not in [2, 4]:  # プレイヤー数は2人または4人のみ許可
        await interaction.response.edit_message(content="プレイヤーは2人または4人のみです。")
        return

    # デッキを初期化して配布
    initialize_deck()  # デッキを生成（詳細は未提示）
    distribute_deck()  # デッキをプレイヤーに分配（詳細は未提示）

    await interaction.response.edit_message(content="ゲームを開始します！")


    # 各プレイヤーに手札を配り、得点を0に初期化
    hand_size = 5 if len(players) == 2 else 3  # プレイヤー人数によって手札枚数を切り替え
    for player in players:
        hands[player] = [deck.pop() for _ in range(hand_size)]
        points[player] = 0



# 現在のゲーム状態を確認する処理
async def handle_check_status(interaction: discord.Interaction):
    if not players:  # プレイヤーがいない場合
        await interaction.response.send_message("現在、ゲームに参加しているプレイヤーはいません。", ephemeral=True)
        return

    # プレイヤーと得点をリストとして表示
    player_list = "\n".join([f"{player.name}: {points.get(player, 0)} 点" for player in players])
    message = f"**現在の参加者と得点**:\n{player_list}"
    await interaction.response.send_message(message, ephemeral=True)



# 決着判定
def check_game_over():
    global points, players, hands, deck

    # 2人プレイの場合
    if len(players) == 2:
        # 山札と全プレイヤーの手札がなくなった場合
        if not deck and all(len(hand) == 0 for hand in hands.values()):
            max_score = max(points.values())
            winners = [player for player, score in points.items() if score == max_score]

            if len(winners) > 1:
                return {"status": "draw", "winners": winners, "points": points}
            else:
                return {"status": "game_over", "winner": winners, "points": points}

        # 20ポイント以上獲得した場合
        for player, score in points.items():
            if score >= 20:
                return {"status": "game_over", "winner": [player], "points": points}

    # 4人プレイの場合
    if len(players) == 4:
        # 山札と全プレイヤーの手札がなくなった場合のみ勝敗判定
        if not deck and all(len(hand) == 0 for hand in hands.values()):
            max_score = max(points.values())
            winners = [player for player, score in points.items() if score == max_score]

            if len(winners) > 1:
                return {"status": "draw", "winners": winners, "points": points}
            else:
                return {"status": "game_over", "winner": winners, "points": points}

    # まだゲームが続行中の場合
    return {"status": "ongoing"}




# ゲーム終了時のリザルト表示
async def show_results(channel, result):
    if result["status"] == "game_over":
        winner_names = ", ".join([player.name for player in result["winner"]])
        await channel.send(
            content=(
                f"ゲーム終了！優勝者: {winner_names}\n\n"
                + "\n".join([f"{player.name}: {score}点" for player, score in result["points"].items()])
            )
        )
    elif result["status"] == "draw":
        draw_names = ", ".join([player.name for player in result["winners"]])
        await channel.send(
            content=(
                f"ゲーム終了！引き分けです: {draw_names}\n\n"
                + "\n".join([f"{player.name}: {score}点" for player, score in result["points"].items()])
            )
        )


# ラウンド終了後に決着を確認
async def handle_round_end(channel):
    
    result = check_game_over()
    if result["status"] in ["game_over", "draw"]:
        await show_results(channel, result)

        global players, points, hands, deck, played_cards, card_stack, tie_count, carry_over_cards, last_victory_message
            
        # ゲーム状態をすべてリセット
        players = []
        points = {}
        hands = {}
        deck = []
        played_cards = {}
        card_stack = []
        tie_count = 0
        carry_over_cards = []
        last_victory_message = None

        return True  # ゲーム終了
    return False





# ボットのトークンを指定（注意: 実際のコードにはトークンをハードコードしないこと）
bot.run(os.getenv("TOKEN"))