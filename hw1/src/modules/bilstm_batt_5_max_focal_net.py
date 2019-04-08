import torch
torch.cuda.manual_seed_all(9487)
import torch.nn.functional as F

class BiLstmBatt5MaxFocalNet(torch.nn.Module):
    """
    Args:
    """

    def __init__(self, dim_embeddings,
                 similarity='MLP'):
        super(BiLstmBatt5MaxFocalNet, self).__init__()
        self.hidden_size = 128
        self.num_layers = 1
        self.rnn = torch.nn.LSTM(dim_embeddings, self.hidden_size, self.num_layers, batch_first=True, bidirectional=True)
        
        self.key_layer = torch.nn.Linear(self.hidden_size * 2, self.hidden_size * 2, bias=False)
        self.query_layer = torch.nn.Linear(self.hidden_size * 2, self.hidden_size * 2, bias=False)
        self.energy_layer = torch.nn.Linear(self.hidden_size * 2, 1, bias=False)
        self.magic_layer = torch.nn.Linear((self.hidden_size * 2) * 2, self.hidden_size * 2)
        self.attention_rnn = torch.nn.LSTM((self.hidden_size * 2) * 5, self.hidden_size, self.num_layers, batch_first=True, bidirectional=True)
        
        self.similarity = torch.nn.Linear((self.hidden_size * 2) * 2, 1, bias=False)
 
    def forward(self, context, context_lens, options, option_lens):
        context_length = context.size(1)

        # Set initial hidden and cell states 
        h_0 = torch.zeros(self.num_layers * 2, context.size(0), self.hidden_size).to(context.get_device())
        c_0 = torch.zeros(self.num_layers * 2, context.size(0), self.hidden_size).to(context.get_device())
        
        # Forward propagate RNN
        # context_outs: tensor of shape (B, Tc, H * 2)
        # context_h_n: tensor of shape (num_layers * 2, B, H)
        # context_c_n: tensor of shape (num_layers * 2, B, H)
        context_outs, (context_h_n, context_c_n) = self.rnn(context, (h_0, c_0))

        # context_key: tensor of shape (B, Tc, H * 2)
        context_key = self.key_layer(context_outs)

        logits = []
        for i, option in enumerate(options.transpose(1, 0)):
            option_length = option.size(1)

            # Set initial hidden and cell states 
            h_0 = torch.zeros(self.num_layers * 2, context.size(0), self.hidden_size).to(context.get_device())
            c_0 = torch.zeros(self.num_layers * 2, context.size(0), self.hidden_size).to(context.get_device())

            # Forward propagate RNN
            # option_outs: tensor of shape (B, To, H * 2)
            # option_h_n: tensor of shape (num_layers * 2, B, H)
            # option_c_n: tensor of shape (num_layers * 2, B, H)
            option_outs, (option_h_n, option_c_n) = self.rnn(option, (h_0, c_0))

            # option_query: tensor of shape (B, To, H * 2)
            option_query = self.query_layer(option_outs)
            
            # repeat_context_key: tensor of shape (B, Tc, H * 2) -> (B, To, Tc, H * 2)
            repeat_context_key = torch.unsqueeze(context_key, 1).expand(-1, option_length, -1, -1)
            # repeat_option_query: tensor of shape (B, To, H * 2) -> (B, To, Tc, H * 2)
            repeat_option_query = torch.unsqueeze(option_query, 2).expand(-1, -1, context_length, -1)
            # attentions: tensor of shape (B, To, Tc, H * 2) -> (B, To, Tc)
            attentions = self.energy_layer(torch.tanh(repeat_option_query + repeat_context_key)).squeeze(dim=-1)
            
            # attention_context: tensor of shape (B, Tc, To) x (B, To, H * 2) -> (B, Tc, H * 2)
            attention_context = torch.bmm(F.softmax(attentions, dim=1).transpose(1, 2), option_outs)
            # attention_option: tensor of shape (B, To, Tc) x (B, Tc, H * 2) -> (B, To, H * 2)
            attention_option = torch.bmm(F.softmax(attentions, dim=2), context_outs)

            # Set initial hidden and cell states 
            h_1 = torch.zeros(self.num_layers * 2, context.size(0), self.hidden_size).to(context.get_device())
            c_1 = torch.zeros(self.num_layers * 2, context.size(0), self.hidden_size).to(context.get_device())

            # Forward propagate RNN
            # attention_context_outs: tensor of shape (B, Tc, H * 2)
            # attention_context_h_n: tensor of shape (num_layers * 2, B, H)
            # attention_context_c_n: tensor of shape (num_layers * 2, B, H)
            attention_context_outs, (attention_context_h_n, attention_context_c_n) = self.attention_rnn(
                torch.cat((
                    context_outs, 
                    attention_context, 
                    torch.mul(context_outs, attention_context), 
                    context_outs - attention_context, 
                    self.magic_layer(torch.cat((context_outs, attention_context), dim=-1))), 
                    dim=-1), (h_1, c_1))

            # Max pooling over RNN outputs.
            # attention_context_outs_max: tensor of shape (B, H * 2)
            attention_context_outs_max = attention_context_outs.max(dim=1)[0]

            # Set initial hidden and cell states 
            h_1 = torch.zeros(self.num_layers * 2, option.size(0), self.hidden_size).to(option.get_device())
            c_1 = torch.zeros(self.num_layers * 2, option.size(0), self.hidden_size).to(option.get_device())

            # Forward propagate RNN
            # attention_option_outs: tensor of shape (B, To, H * 2)
            # attention_option_h_n: tensor of shape (num_layers * 2, B, H)
            # attention_option_c_n: tensor of shape (num_layers * 2, B, H)
            attention_option_outs, (attention_option_h_n, attention_option_c_n) = self.attention_rnn(
                torch.cat((
                    option_outs, 
                    attention_option, 
                    torch.mul(option_outs, attention_option), 
                    option_outs - attention_option, 
                    self.magic_layer(torch.cat((option_outs, attention_option), dim=-1))), 
                    dim=-1), (h_1, c_1))

            # Max pooling over RNN outputs.
            # attention_option_outs_max: tensor of shape (B, H * 2)
            attention_option_outs_max = attention_option_outs.max(dim=1)[0]

            # Cosine similarity between context and each option.
            # logit = torch.nn.CosineSimilarity(dim=1)(attention_context_outs_max, attention_option_outs_max)
            logit = self.similarity(torch.cat((attention_context_outs_max, attention_option_outs_max), dim=-1))[:, 0]
            logits.append(logit)

        logits = F.softmax(torch.stack(logits, 1), dim=1)
        return logits